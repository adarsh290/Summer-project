from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, Property
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app.utils.logger import logger
from app.database.connection import db
from app.models.image import Image
from app.models.face import Face
from app.services.face_service import FaceService
from app.services.clustering_service import ClusteringService

# Batch DB commits every N images instead of every 1
_FACE_DB_BATCH_SIZE = 20


class FaceScanWorker(QRunnable):
    """Background worker to extract faces and cluster them without freezing the UI.
    
    Optimized with:
    - Bulk DB queries: one query to fetch all paths, one bulk delete for old faces
    - Pipelined image loading: a background thread pre-reads the next image from
      disk while the GPU processes the current one
    - Batched DB commits every _FACE_DB_BATCH_SIZE images
    """
    
    class Signals(QObject):
        progress = Signal(int, int)  # current, total
        finished = Signal()
        error = Signal(str)
        statusText = Signal(str)

    def __init__(self, image_ids: list[int]):
        super().__init__()
        self.image_ids = image_ids
        self.signals = self.Signals()
        self.face_service = FaceService()
        self.clustering_service = ClusteringService()

    def run(self):
        try:
            self.signals.statusText.emit("Initializing ML Models...")
            if not self.face_service._init_model():
                self.signals.error.emit("ML dependencies not found. Run pip install insightface onnxruntime-gpu")
                return

            import cv2
            session = db.SessionLocal()
            total = len(self.image_ids)

            try:
                # Bulk pre-fetch all image paths in one query
                all_images = session.query(Image.id, Image.original_path).filter(
                    Image.id.in_(self.image_ids)
                ).all()
                image_map = {img.id: img.original_path for img in all_images if img.original_path}

                # Bulk delete old faces and their crops
                old_faces = session.query(Face).filter(Face.image_id.in_(list(image_map.keys()))).all()
                for f in old_faces:
                    if f.face_crop_path and os.path.exists(f.face_crop_path):
                        try:
                            os.remove(f.face_crop_path)
                        except Exception as e:
                            logger.warning(f"Could not remove old face crop: {e}")
                
                session.query(Face).filter(Face.image_id.in_(list(image_map.keys()))).delete(
                    synchronize_session=False
                )
                session.commit()

                def _preload_image(path: str):
                    try:
                        return cv2.imread(path)
                    except Exception:
                        return None

                pending_since_commit = 0
                work_list = [(img_id, image_map[img_id]) for img_id in self.image_ids if img_id in image_map]

                with ThreadPoolExecutor(max_workers=1, thread_name_prefix="img_preload") as preloader:
                    preload_future = None
                    preload_img_id = None

                    for i, (img_id, img_path) in enumerate(work_list):
                        self.signals.progress.emit(i, total)
                        self.signals.statusText.emit(f"Scanning face {i + 1}/{total}")

                        # Get image: from pre-loaded future or read now
                        if preload_future is not None and preload_img_id == img_id:
                            cv_img = preload_future.result()
                        else:
                            cv_img = cv2.imread(img_path)

                        # Submit NEXT image for pre-loading (pipeline)
                        if i + 1 < len(work_list):
                            next_id, next_path = work_list[i + 1]
                            preload_future = preloader.submit(_preload_image, next_path)
                            preload_img_id = next_id
                        else:
                            preload_future = None

                        if cv_img is None:
                            continue

                        # GPU inference
                        results = self.face_service.detect_faces_from_array(cv_img, img_path)

                        for res in results:
                            l, t, r, b = res['bbox']
                            face = Face(
                                image_id=img_id,
                                bbox_left=l,
                                bbox_top=t,
                                bbox_right=r,
                                bbox_bottom=b,
                                embedding=res['embedding'],
                                face_crop_path=res['crop_path']
                            )
                            session.add(face)

                        pending_since_commit += 1
                        if pending_since_commit >= _FACE_DB_BATCH_SIZE:
                            session.commit()
                            pending_since_commit = 0

                if pending_since_commit > 0:
                    session.commit()

                self.signals.statusText.emit("Clustering faces...")
                self.clustering_service.cluster_faces()
                self.signals.finished.emit()

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Face scan worker error: {e}")
            self.signals.error.emit(str(e))


class ModelPrewarmWorker(QRunnable):
    """Lightweight worker that initializes InsightFace models in the background.
    
    Started when a scan begins so the ~40s model load overlaps with scanning.
    The models are stored in the shared FaceService singleton so the actual
    face scan skips initialization entirely.
    """

    class Signals(QObject):
        finished = Signal(bool)  # success

    def __init__(self, face_service: FaceService):
        super().__init__()
        self.face_service = face_service
        self.signals = self.Signals()
        self.setAutoDelete(True)

    def run(self):
        logger.info("Pre-warming InsightFace model during scan...")
        success = self.face_service._init_model()
        if success:
            logger.info("InsightFace model pre-warmed successfully.")
        else:
            logger.warning("InsightFace model pre-warm failed (will retry on face scan).")
        self.signals.finished.emit(success)


class FaceController(QObject):
    """QML interface for face detection and clustering operations."""
    
    scanStarted = Signal()
    scanProgressChanged = Signal()
    scanFinished = Signal()
    scanError = Signal(str)
    statusTextChanged = Signal()

    def __init__(self):
        super().__init__()
        self._thread_pool = QThreadPool.globalInstance()
        self._is_scanning = False
        self._progress_current = 0
        self._progress_total = 0
        self._status_text = ""
        self._shared_face_service = FaceService()  # Shared instance for pre-warming
        self._model_ready = False

    # ── Properties ────────────────────────────────────────────────────────
    
    isScanningChanged = Signal()

    @Property(bool, notify=isScanningChanged)
    def isScanning(self) -> bool:
        return self._is_scanning

    @Property(int, notify=scanProgressChanged)
    def progressCurrent(self) -> int:
        return self._progress_current

    @Property(int, notify=scanProgressChanged)
    def progressTotal(self) -> int:
        return self._progress_total

    @Property(str, notify=statusTextChanged)
    def statusText(self) -> str:
        return self._status_text

    def _set_is_scanning(self, val: bool):
        if self._is_scanning != val:
            self._is_scanning = val
            self.isScanningChanged.emit()
            self.scanStarted.emit() if val else self.scanFinished.emit()

    def _set_status(self, text: str):
        if self._status_text != text:
            self._status_text = text
            self.statusTextChanged.emit()

    # ── Pre-warming ───────────────────────────────────────────────────────

    def prewarmModel(self):
        """Start loading the ML model in the background.
        
        Called by ScanController when a scan starts so the ~40s model 
        initialization overlaps with the scan instead of happening after.
        """
        if self._model_ready or self._shared_face_service._is_initialized:
            return  # Already loaded or loading

        worker = ModelPrewarmWorker(self._shared_face_service)
        worker.signals.finished.connect(self._on_prewarm_finished)
        self._thread_pool.start(worker)

    def _on_prewarm_finished(self, success: bool):
        self._model_ready = success

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot()
    def startFaceScan(self):
        """Starts the background face scan on all available images."""
        if self._is_scanning:
            return
            
        session = db.SessionLocal()
        try:
            images = session.query(Image.id).all()
            image_ids = [img.id for img in images]
        finally:
            session.close()
            
        if not image_ids:
            self.scanError.emit("No images to scan.")
            return

        self._set_is_scanning(True)
        self._progress_current = 0
        self._progress_total = len(image_ids)
        self._set_status("Starting face scan...")
        self.scanProgressChanged.emit()
        
        worker = FaceScanWorker(image_ids=image_ids)
        # Share the pre-warmed model so it skips the 40s init
        worker.face_service = self._shared_face_service
        worker.signals.progress.connect(self._on_progress)
        worker.signals.statusText.connect(self._set_status)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        
        self._thread_pool.start(worker)

    def _on_progress(self, current: int, total: int):
        self._progress_current = current
        self._progress_total = total
        self.scanProgressChanged.emit()

    def _on_finished(self):
        self._set_is_scanning(False)
        self._set_status("Scan complete.")

    def _on_error(self, err_msg: str):
        self._set_is_scanning(False)
        self._set_status(f"Error: {err_msg}")
        self.scanError.emit(err_msg)

    @Slot(result="QVariantList")
    def getPeople(self):
        """Returns a list of clustered people with their profile pictures."""
        session = db.SessionLocal()
        try:
            from app.models.person import Person
            from app.models.face import Face
            
            people = session.query(Person).all()
            results = []
            for p in people:
                pfp_path = ""
                if p.profile_face_id:
                    face = session.query(Face).filter(Face.id == p.profile_face_id).first()
                    if face and face.face_crop_path:
                        pfp_path = Path(face.face_crop_path).resolve().as_uri()
                        
                face_count = session.query(Face).filter(Face.person_id == p.id).count()
                
                results.append({
                    "personId": p.id,
                    "name": p.name,
                    "profilePath": pfp_path,
                    "faceCount": face_count
                })
            
            results.sort(key=lambda x: x["faceCount"], reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to fetch people: {e}")
            return []
        finally:
            session.close()

    @Slot(int, result="QVariantList")
    def getPhotosForPerson(self, person_id: int):
        """Returns a list of image dicts (originalPath, thumbnailPath) for a specific person."""
        session = db.SessionLocal()
        try:
            from app.models.face import Face
            from app.models.image import Image
            
            faces = session.query(Face).filter(Face.person_id == person_id).all()
            
            results = []
            seen_image_ids = set()
            for face in faces:
                if face.image_id in seen_image_ids:
                    continue
                seen_image_ids.add(face.image_id)
                
                img = session.query(Image).filter(Image.id == face.image_id).first()
                if img:
                    results.append({
                        "id": img.id,
                        "originalPath": Path(img.original_path).resolve().as_uri() if img.original_path else "",
                        "thumbnailPath": Path(img.thumbnail_path).resolve().as_uri() if img.thumbnail_path else "",
                        "displayRotation": img.display_rotation
                    })
            return results
        except Exception as e:
            logger.error(f"Failed to fetch photos for person {person_id}: {e}")
            return []
        finally:
            session.close()
