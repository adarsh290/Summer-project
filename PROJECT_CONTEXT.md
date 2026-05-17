# Proximi Project Context

## Current Milestone
**Milestone 7 — Session & Disk Space Management**  
Focus: Refactoring Proximi into a strictly session-based tool. Implementing robust cleanup routines that wipe all ephemeral data (thumbnails, databases, face crops, logs, trash) on application exit and startup, ensuring zero residual disk footprint between sessions. Identifies identical photos to keep the highest-quality version.

---

## Architecture Overview

| Layer | Technology |
|-------|-----------|
| UI | Qt Quick / QML |
| Backend Bridge | PySide6 |
| Database | SQLite via SQLAlchemy |
| Thumbnail Engine | Pillow |
| Async Pattern | QThreadPool + QRunnable |
| CV Pipeline | imagehash, scikit-image, networkx |
| Architecture | Layered (UI → Controllers → Services → Repository) |

**Python Dependencies:**  
`Python 3.11+`, `PySide6`, `SQLAlchemy`, `Pillow`, `imagehash`, `scikit-image`, `networkx`, `scipy`, `numpy`, `psutil`

---

## Folder Structure

```
app/
├── controllers/
│   ├── app_controller.py
│   ├── scan_controller.py          # Scan lifecycle + ImageViewModel
│   ├── similarity_controller.py    # Similarity pipeline + group review
│   ├── cleanup_controller.py       # Selection state + cleanup execution
│   └── debug_controller.py
├── services/
│   ├── scan_service.py
│   ├── scan_worker.py
│   ├── thumbnail_service.py
│   ├── hash_service.py
│   ├── duplicate_service.py        # Exact duplicate detection logic
│   ├── duplicate_worker.py         # Async exact duplicate worker
│   ├── similarity_service.py
│   ├── grouping_service.py
│   ├── similarity_worker.py
│   ├── trash_service.py            # Move-to-trash + restore logic
│   ├── folder_service.py
│   └── debug_service.py
├── database/
│   ├── connection.py
│   ├── base.py                     # Declarative base
│   ├── migration.py
│   ├── image_repository.py
│   ├── group_repository.py
│   └── trash_repository.py         # Trash record CRUD
├── models/
│   ├── image.py
│   ├── scan_session.py
│   ├── group.py
│   ├── group_member.py
│   └── trash_record.py             # New in M4
└── ui/qml/
    ├── Main.qml
    ├── themes/Theme.qml
    └── components/
        ├── TopBar.qml
        ├── Sidebar.qml
        ├── ContentArea.qml
        ├── Footer.qml              # Toast notifications
        ├── EmptyState.qml
        ├── ImageCard.qml           # Selection states (keeper/rejected)
        ├── GroupReviewView.qml     # Main review + keyboard shortcuts
        ├── ActionBar.qml           # Cleanup action buttons
        ├── ImagePreviewModal.qml   # Fullscreen lightbox (F key)
        └── ReviewCompleteState.qml # End-of-review summary screen
data/                               # Ephemeral session data (wiped on exit)
├── thumbnails/                     # Cached thumbnails
├── trash/                          # App-managed trash (not OS trash)
├── logs/                           # App logs
├── cache/                          # General cache
├── faces/                          # Cropped ML profile pictures
└── proximi.db                      # SQLite database
```

---

## Database Tables

### images
| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK, autoincrement |
| original_path | String | unique, indexed |
| file_name | String | |
| extension | String | |
| width | Integer | nullable |
| height | Integer | nullable |
| file_size | Integer | |
| created_at | DateTime | auto |
| modified_at | DateTime | file mtime |
| thumbnail_path | String | nullable |
| scan_session_id | Integer | FK → scan_sessions |
| phash | String | nullable |
| dhash | String | nullable |
| hash_computed_at | DateTime | nullable |

### scan_sessions
| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK, autoincrement |
| folder_path | String | |
| started_at | DateTime | auto |
| completed_at | DateTime | nullable |
| images_found | Integer | default 0 |
| status | String | in_progress/completed/failed |

### groups
| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK, autoincrement |
| group_type | String | 'similar' or 'burst' |
| similarity_score | Float | |
| created_at | DateTime | |
| scan_session_id | Integer | FK → scan_sessions |
| version | Integer | Default 1 |
| representative_image_id | Integer | FK → images |

### group_members
| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK, autoincrement |
| group_id | Integer | FK → groups |
| image_id | Integer | FK → images |
| added_at | DateTime | |

### trash_records *(New — Milestone 4)*
| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK, autoincrement |
| original_path | String | original file location |
| trash_path | String | unique, location inside `data/trash/` |
| deleted_at | DateTime | auto (UTC) |
| restored_at | DateTime | nullable, set on undo/restore |
| group_id | Integer | FK → groups (nullable) |
| scan_session_id | Integer | FK → scan_sessions |
| image_id | Integer | FK → images |
| batch_id | String | UUID hex, groups records for batch undo |

---

## Services

### ScanService
- Recursive image discovery (`.jpg`, `.jpeg`, `.png`, `.webp`)
- Pipeline: discovery → metadata → DB persist → thumbnail gen → UI update
- Progress reporting via callbacks; cancellation-aware

### ThumbnailService
- Pillow thumbnail generation (max 256px, LANCZOS)
- Deterministic cache keys: `SHA256(normalized_path + mtime)`
- Cached as WEBP to `data/thumbnails/`

### HashService
- Computes perceptual hashes (`pHash`, `dHash`) using `imagehash`
- Incremental — skips already-hashed images

### SimilarityService
- Candidate filtering via pHash Hamming distance (threshold ≤ 7)
- SSIM-based refinement via `scikit-image`

### GroupingService
- Adjacency graph via `networkx`; clusters with connected components
- Persists groups of min size 2; assigns representative node by centrality

### DuplicateService *(New — Milestone 5)*
- Finds exact perceptual duplicates via pHash and dHash
- Automatically keeps the highest-quality version (largest file size)
- Moves duplicates directly to `data/trash/` using `TrashService`

### FaceService *(New — Milestone 6)*
- Handles GPU-accelerated facial detection and embedding extraction using `insightface` (`buffalo_l` model)
- Persists extracted face bounding boxes and crops to `data/faces/` for profile pictures
- Falls back to CPU if `onnxruntime-gpu` is not available

### ClusteringService *(New — Milestone 6)*
- Performs unsupervised clustering of 512-d mathematical embeddings using `scikit-learn` DBSCAN algorithm
- Persists clusters into the `people` and `faces` tables in the database

### TrashService *(New — Milestone 4)*
- `move_to_trash(files, batch_id, keeper_id)` — moves files to `data/trash/`
- Filename collision handling: `original__shortuuid.ext` (readable + unique)
- **Keeper Protection (Rule 6):** Service-layer check prevents keeper images from being trashed even if UI state has bugs
- `restore_batch(batch_id)` — restores all files in a batch by batch UUID
- Returns `(moved_count, freed_bytes)` for feedback messages

### ScanWorker, SimilarityWorker, DuplicateWorker & FaceScanWorker (QRunnable)
- Async workers on QThreadPool with progress reporting and cancellation support

---

## Controllers

### ScanController
- Native folder dialog, scan lifecycle management
- `ImageViewModel.from_image(img)` — enriched view-model including `imageId`, `width`, `height`, `fileSize`, `modifiedAt`
- `removeExactDuplicates()` — background execution of exact duplicate removal using `DuplicateWorker`

### SimilarityController
- Orchestrates hashing → similarity → grouping pipeline
- Group review state: `currentGroupIndex`, `groupCount`, `reviewComplete`
- `reviewComplete` property: set when user navigates past the last group
- `skipGroup()` — advance without cleanup action

### CleanupController *(New — Milestone 4)*
- `selectionState: dict` — `{imageId: "keeper" | "rejected" | "unselected"}`
- Auto-keeper heuristic on group load: best resolution → largest file → earliest modified
- `setKeeper(imageId)` — explicit keeper assignment (clears old keeper in group)
- `toggleSelection(imageId)` — toggle unselected ↔ rejected
- `selectAllExceptKeeper()` — mark all non-keepers rejected
- `executeCleanup()` — move rejected images to trash, auto-advance if successful
- `undoLastCleanup()` — restore last batch, navigate back
- `actionCompleted(str)` signal — carries feedback message for Footer toast

### FaceController *(New — Milestone 6)*
- Orchestrates facial detection and DBSCAN clustering via `FaceScanWorker`
- Exposes `getPeople()` and `getPhotosForPerson(person_id)` as QML-accessible data bridges
- Provides reactive `@Property` for `isScanning`, `progressCurrent`, and `statusText`

### DebugController
- Toggle via `Ctrl+Shift+D`
- Snapshot includes cleanup metrics (`cleanupDeleted`, `cleanupRestored`, `cleanupUndos`)

### DebugService Cleanup Metrics *(New — Milestone 4)*
- `cleanup_executed(count)` — increments `deleted_count`
- `undo_executed(count)` — increments `restored_count` and `undo_operations`

---

## QML Components

### ImageCard
- Properties: `thumbnailSource`, `fileName`, `imageId`, `selectionState`
- States: `unselected` (default) | `keeper` (green border + ✓ badge) | `rejected` (red overlay + ✕ badge)
- Single click: focus image
- Double click: `cleanupController.setKeeper(imageId)`
- Keyboard: `K` = keeper, `X`/`R` = reject, `Space` = toggle reject, `F`/`Enter` = preview
- Signal: `requestPreview()`

### GroupReviewView
- Hosts `GridView` + `ActionBar` in `ColumnLayout`
- Embeds `ImagePreviewModal` (z=100) and `ReviewCompleteState` (z=50)
- Keyboard shortcuts: `→`/`D` next, `←`/`A` prev, `Ctrl+Z` undo, `Ctrl+Enter` execute cleanup

### ActionBar *(New — Milestone 4)*
- Buttons: "Reject Others", "Skip", "Execute Cleanup"
- Hidden when `reviewComplete` is true
- "Execute Cleanup" disabled when `rejectedCount === 0`

### ImagePreviewModal *(New — Milestone 4)*
- Fullscreen lightbox overlay (dim background + `Image.PreserveAspectFit`)
- Open via `openPreview(src)` call; close via `Escape`, `F`, or ✕ button
- Smooth open/close via `Behavior on opacity`

### ReviewCompleteState *(New — Milestone 4)*
- Shown when `similarityController.reviewComplete === true`
- Displays: total groups reviewed, total images cleaned
- Actions: "Undo Last Action" (if `canUndo`), "Review Again"

### PeopleView & PersonGalleryView *(New — Milestone 6)*
- Dedicated navigation space for viewing clustered faces and people
- `PeopleView` renders circular profile pictures representing each cluster using cached `data/faces/` crops
- `PersonGalleryView` filters the image grid to display only photos where a specific person is detected

### Footer
- Left: status text — switches to toast message for ~2 seconds after cleanup actions
- Right: total scanned image count
- Toast driven by `cleanupController.actionCompleted` signal + `Timer { interval: 2000 }`

### Sidebar (Group Review Mode)
- Group index, image count, type badge, similarity score
- Cleanup stats: "Cleaned Images" counter from `debugController.metrics.cleanupDeleted`
- Navigation: Previous / Next group buttons

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+D` | Toggle debug panel |
| `→` / `D` | Next similarity group |
| `←` / `A` | Previous similarity group |
| `K` | Mark focused image as keeper |
| `X` / `R` | Mark focused image as rejected |
| `Space` | Toggle reject on focused image |
| `F` / `Enter` | Open full-screen image preview |
| `Ctrl+Enter` | Execute cleanup (move rejected to trash) |
| `Ctrl+Z` | Undo last cleanup batch |
| `Escape` | Close preview modal |

---

## Coding Standards
- Python: Type hints, meaningful naming, composition over inheritance, isolated logic.
- QML: Presentation logic only — zero business logic.
- Architecture: No global state. QML communicates with Python via QObject / Signals / Slots only.
- Controllers: Each controller owns one domain (scan, similarity, cleanup, debug).
- Safety: Destructive operations require explicit intent; reversibility is mandatory.

---

## Agent Rules
- QML files must contain presentation/UI logic ONLY.
- Python backend handles state, logic, and DB operations.
- Do not overengineer (no DI frameworks, plugin systems, Redux-like patterns).
- Evolve incrementally — do not create modules/directories until the milestone requires them.

---

## Completed Features

### Milestone 1 — Foundation
- Project structure and SQLite initialization
- QML application shell (Main, Sidebar, TopBar, Footer, ContentArea)
- Folder preparation routines
- Basic controller and service layer scaffolding

### Milestone 2 — Scan & Thumbnail Engine
- Native folder selection dialog
- Recursive async image scanning (QThreadPool)
- Pillow thumbnail generation + WEBP cache (SHA256 keys)
- SQLite metadata persistence (images + scan_sessions)
- Progressive thumbnail GridView with scroll
- Empty / Loading / Loaded UI states
- ImageViewModel layer (filesystem path → file URI)
- Internal debug panel with runtime metrics
- DB migration infrastructure (ALTER TABLE pattern)

### Milestone 3 — Similarity Engine & Grouping
- pHash + dHash computation via `imagehash`
- Similarity candidate filtering (Hamming distance ≤ 7)
- SSIM refinement via `scikit-image`
- Graph-based clustering via `networkx` connected components
- Group and GroupMember ORM models
- GroupRepository CRUD layer
- SimilarityWorker async pipeline
- GroupReviewView (thumbnail grid per group)
- Sidebar group review panel (index, count, type/score)
- Unified scan workflow (Browse → Start Scan → Rescan)

### Milestone 4 — Cleanup Workflow & Safe Deletion
- `TrashRecord` ORM model + auto-migration
- `TrashRepository` (bulk create, batch restore, stats)
- `TrashService` (move-to-trash, filename collision via `original__uuid.ext`, keeper protection at service layer, batch restore)
- `CleanupController` (selection state, auto-keeper heuristic, executeCleanup, undoLastCleanup)
- `ImageCard` selection states (keeper ✓ green border, rejected ✕ red overlay, unselected)
- `ActionBar` QML component (Reject Others, Skip, Execute Cleanup)
- `ImagePreviewModal` fullscreen lightbox
- `ReviewCompleteState` end-of-review summary screen
- Footer toast notifications after cleanup actions (2s visible)
- Keyboard shortcut system (K, X, Ctrl+Enter, Ctrl+Z, F, arrows)
- Sidebar cleanup stats (Cleaned Images counter)
- Debug panel Cleanup metrics section
- `reviewComplete` property + auto-advance on successful cleanup

### Milestone 5 — Exact Duplicate Removal *(Current)*
- `DuplicateService` (Hash-based exact duplicate detection, keeper selection by file size)
- `DuplicateWorker` (Async worker for duplicate removal)
- `ScanController` integration with `removeExactDuplicates()`
- TopBar UI integration with "Clean Duplicates" button

### Milestone 7 — Session & Disk Space Management *(Current)*
- Transitioned application to a strict stateless, session-based architecture.
- Added graceful lock releasing for `proximi.log` and `proximi.db` via `shutdown_logger()` and `db.close_database()`.
- Implemented `cleanup_startup` and `cleanup_data_directory` in `FolderService` to completely wipe all cached thumbnails, face crops, trash records, and databases on application launch and exit.
- Integrated disk space cleanup directly into the `ClusteringService` to delete non-profile-picture face crops immediately after person clustering.

---

## Known Issues
- None identified post-Milestone 7.

## Next Planned Milestone
- Milestone 8: TBD (Candidates: export reports, UI transition animations)
