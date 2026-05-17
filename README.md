# Proximi

A local-first desktop photo management application built with Python and Qt Quick.

Proximi helps you organize, scan, browse, and **safely clean up** large image collections with a responsive, modern interface — all without cloud dependencies.

**Session-Based Architecture**: Proximi is designed as a strict session-based tool. You open it, scan a folder, do your cleanup, and close it. On exit, all databases, caches, logs, and generated files are completely wiped, leaving zero residual disk footprint on your machine.

---

## Features

- **Folder Scanning** — Recursively discover images (JPG, PNG, WEBP)
- **Async Thumbnail Pipeline** — Background generation with persistent WEBP cache
- **SQLite Metadata** — All image metadata stored locally for fast queries
- **Progressive Grid** — Virtualized rendering for smooth scrolling through 1000+ images
- **Exact Duplicate Removal** — Hash-based duplicate detection service to instantly identify identical photos and keep the highest-quality version
- **Similarity Detection** — Classical CV pipeline (pHash, dHash, SSIM) to find duplicates and burst shots
- **Duplicate Cleanup** — Review groups, mark keepers, reject duplicates, and move to app-managed trash
- **Safe Deletion** — Files are never permanently deleted — moved to `data/trash/` with one-step undo
- **Facial Recognition** — Uses local machine learning (`insightface` & `onnxruntime-gpu`) to detect and group faces securely on your device
- **People Gallery** — Automatically organizes photos by people with automatic profile pictures
- **Keyboard-Driven Review** — Rapid group navigation and selection using keyboard shortcuts
- **Full-Screen Preview** — Inspect images in a lightweight lightbox before making decisions
- **Debug Panel** — Built-in diagnostics overlay (`Ctrl+Shift+D`) for runtime inspection

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Qt Quick / QML |
| Backend | Python 3.11+, PySide6 |
| Database | SQLite via SQLAlchemy |
| Imaging | Pillow, OpenCV |
| Similarity | imagehash, scikit-image, networkx |
| Machine Learning | insightface, onnxruntime-gpu, scikit-learn (DBSCAN) |
| Architecture | Layered (UI → Controllers → Services → Repository) |

---

## Getting Started

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/adarsh290/Summer-project.git
cd Summer-project

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

---

## Usage

### Scanning

1. Click **Browse Folder** in the main area to choose an image directory
2. Click **Start Scan** to begin async image discovery and thumbnail generation
3. Browse your images in the responsive grid
4. After scanning, use **Rescan** or **Find Similar** from the top bar

### Duplicate Review & Cleanup

1. Click **Find Similar** to run the similarity detection pipeline
2. Groups of similar/burst images appear in the sidebar
3. Navigate groups with `→` / `←` arrow keys
4. Within a group:
   - The best image is **auto-selected as keeper** (highest resolution)
   - Press `K` to manually set a keeper
   - Press `X` or `R` to mark images as rejected
   - Press `F` or double-click to open full-screen preview
5. Press `Ctrl+Enter` to execute cleanup (move rejected images to trash)
6. The app auto-advances to the next group on success
7. Press `Ctrl+Z` to undo the last cleanup action at any time

### Safety

- Files are **never permanently deleted** — moved to `data/trash/`
- Keeper images are **protected at the service layer** even if UI state has bugs
- Cleanup only proceeds if **all file operations succeed**

---

## Project Structure

```
Summer-project/
├── main.py                             # Application entry point
├── requirements.txt
├── PROJECT_CONTEXT.md                  # Full architecture documentation
├── app/
│   ├── controllers/
│   │   ├── app_controller.py
│   │   ├── scan_controller.py          # Scan lifecycle + ImageViewModel
│   │   ├── similarity_controller.py    # Similarity pipeline + group review
│   │   ├── cleanup_controller.py       # Selection state + trash operations
│   │   └── debug_controller.py
│   ├── services/
│   │   ├── scan_service.py
│   │   ├── scan_worker.py
│   │   ├── thumbnail_service.py
│   │   ├── hash_service.py
│   │   ├── similarity_service.py
│   │   ├── grouping_service.py
│   │   ├── similarity_worker.py
│   │   ├── trash_service.py            # Move-to-trash + restore
│   │   ├── face_service.py             # ML face detection/embeddings
│   │   ├── clustering_service.py       # DBSCAN facial clustering
│   │   └── debug_service.py
│   ├── database/
│   │   ├── connection.py
│   │   ├── base.py
│   │   ├── migration.py
│   │   ├── image_repository.py
│   │   ├── group_repository.py
│   │   └── trash_repository.py
│   ├── models/
│   │   ├── image.py
│   │   ├── scan_session.py
│   │   ├── group.py
│   │   ├── group_member.py
│   │   └── trash_record.py
│   └── ui/qml/
│       ├── Main.qml
│       ├── themes/Theme.qml
│       └── components/
│           ├── TopBar.qml
│           ├── Sidebar.qml
│           ├── ContentArea.qml
│           ├── Footer.qml
│           ├── EmptyState.qml
│           ├── ImageCard.qml           # Keeper/Rejected states
│           ├── GroupReviewView.qml
│           ├── ActionBar.qml
│           ├── ImagePreviewModal.qml   # Fullscreen lightbox
│           └── ReviewCompleteState.qml # End-of-review screen
└── data/                               # Ephemeral session data (wiped on exit)
    ├── thumbnails/                     # Cached WEBP thumbnails
    ├── trash/                          # App-managed trash (not OS trash)
    ├── logs/                           # App logs
    ├── cache/                          # General cache
    ├── faces/                          # Cropped ML profile pictures
    └── proximi.db                      # SQLite database
```

---

## Architecture

```
QML (presentation only)
  ↓ signals/slots
Controllers (orchestration, view-model transforms)
  ↓
Services (business logic, async workers)
  ↓
Repository (database persistence)
```

- **QML** handles layout and rendering — zero business logic
- **Controllers** bridge Python ↔ QML, expose typed view-models
- **Services** handle scanning, thumbnailing, similarity, and safe deletion
- **Repository** abstracts all SQLite operations

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

## Milestones

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1 — Foundation | ✅ Complete | Project structure, DB init, QML shell |
| M2 — Scan & Thumbnails | ✅ Complete | Async scan, Pillow thumbnails, SQLite metadata |
| M3 — Similarity Engine | ✅ Complete | pHash/dHash/SSIM pipeline, NetworkX grouping, Group Review UI |
| M4 — Cleanup Workflow | ✅ Complete | Trash system, keeper selection, undo, keyboard shortcuts, lightbox |
| M5 — Exact Duplicates | ✅ Complete | Hash-based duplicate detection, automatic highest-quality keeper selection |
| M6 — Facial Segregation | ✅ Complete | Insightface bounding boxes, embeddings, and DBSCAN clustering with People View |
| M7 — Session Management | ✅ Complete | Stateless architecture, lock releasing, and auto-wiping of the `data/` directory |
| M8 — TBD | ⏳ Planned | Candidates: export reports, UI transition animations |

---

## License

This project is for educational and personal use.
