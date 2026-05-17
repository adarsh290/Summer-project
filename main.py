import sys
import os
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication  # Needed for QFileDialog

from app.utils.logger import logger
from app.services.folder_service import FolderService
from app.services.settings_service import SettingsService
from app.services.thumbnail_service import ThumbnailService
from app.services.scan_service import ScanService
from app.services.debug_service import DebugService
from app.database.connection import db
from app.database.image_repository import ImageRepository
from app.controllers.app_controller import AppController
from app.controllers.settings_controller import SettingsController
from app.controllers.scan_controller import ScanController
from app.controllers.debug_controller import DebugController
from app.controllers.similarity_controller import SimilarityController
from app.services.hash_service import HashService
from app.services.similarity_service import SimilarityService
from app.services.grouping_service import GroupingService
from app.database.group_repository import GroupRepository
from app.database.trash_repository import TrashRepository
from app.services.trash_service import TrashService
from app.controllers.cleanup_controller import CleanupController
from app.controllers.face_controller import FaceController
from app.services.duplicate_service import DuplicateService

def main():
    # 1. Initialize environment and folders
    folder_service = FolderService()
    folder_service.cleanup_startup()
    folder_service.ensure_data_directories()
    
    # 2. Initialize Database
    from app.database.migration import run_migrations
    run_migrations()
    db.initialize_database()
    
    # 3. Setup Application
    # Using QApplication (not QGuiApplication) to support QFileDialog
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    
    # Add themes directory to import paths for the pragma Singleton
    ui_dir = Path(__file__).parent / "app" / "ui" / "qml"
    engine.addImportPath(str(ui_dir))

    # 4. Initialize Services
    settings_service = SettingsService()
    image_repository = ImageRepository()
    group_repository = GroupRepository()
    trash_repository = TrashRepository()
    debug_service = DebugService(image_repository)
    thumbnail_service = ThumbnailService(debug_service=debug_service)
    scan_service = ScanService(image_repository, thumbnail_service, debug_service=debug_service)
    
    hash_service = HashService(image_repository, debug_service)
    sim_service = SimilarityService(image_repository, debug_service)
    grouping_service = GroupingService(group_repository, debug_service)
    trash_service = TrashService(trash_repository, folder_service)
    duplicate_service = DuplicateService(image_repository, trash_service)
    
    # 5. Initialize Controllers
    app_controller = AppController()
    settings_controller = SettingsController(settings_service)
    face_controller = FaceController()  # Created early — injected into scan_controller for pipelined face detection
    scan_controller = ScanController(scan_service, duplicate_service, image_repository, debug_service, face_controller=face_controller)
    debug_controller = DebugController(debug_service)
    similarity_controller = SimilarityController(
        hash_service, 
        sim_service, 
        grouping_service, 
        group_repository, 
        debug_service,
        settings_controller=settings_controller
    )
    cleanup_controller = CleanupController(trash_service, similarity_controller, image_repository, debug_service, scan_controller=scan_controller)
    
    # 5.5 Connect cross-controller signals
    scan_controller.duplicateRemovalFinished.connect(lambda _: cleanup_controller._refresh_staged_count())
    
    # 6. Register context properties (Python -> QML bridge)
    context = engine.rootContext()
    context.setContextProperty("appController", app_controller)
    context.setContextProperty("settingsController", settings_controller)
    context.setContextProperty("scanController", scan_controller)
    context.setContextProperty("debugController", debug_controller)
    context.setContextProperty("similarityController", similarity_controller)
    context.setContextProperty("cleanupController", cleanup_controller)
    context.setContextProperty("faceController", face_controller)
    
    # 7. Load QML
    main_qml = ui_dir / "Main.qml"
    
    # ── Hot Reloading setup ───────────────────────────────────────────
    from PySide6.QtCore import QFileSystemWatcher, QTimer

    class HotReloader:
        def __init__(self, engine, main_qml_path, ui_dir):
            self.engine = engine
            self.main_qml_path = main_qml_path
            self.watcher = QFileSystemWatcher()
            self.timer = QTimer()
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.reload)
            
            # Watch all directories and QML files
            for root, dirs, files in os.walk(ui_dir):
                self.watcher.addPath(root)
                for file in files:
                    if file.endswith('.qml'):
                        self.watcher.addPath(os.path.join(root, file))
            
            self.watcher.fileChanged.connect(self.on_changed)
            self.watcher.directoryChanged.connect(self.on_changed)
            logger.info("Hot reloading enabled for QML files.")

        def on_changed(self, path):
            # Debounce file save events
            self.timer.start(150)
            # Re-add to watcher in case of atomic saves replacing the file
            if os.path.exists(path) and os.path.isfile(path):
                self.watcher.addPath(path)

        def reload(self):
            logger.info("Hot reloading QML...")
            old_windows = self.engine.rootObjects()
            geom = None
            if old_windows:
                geom = old_windows[0].geometry()
                
            self.engine.clearComponentCache()
            self.engine.load(os.fspath(self.main_qml_path))
            
            new_windows = self.engine.rootObjects()
            if new_windows and old_windows:
                new_window = new_windows[-1]
                if geom:
                    new_window.setGeometry(geom)
                
                # Close the old window(s)
                for win in old_windows:
                    if win != new_window:
                        win.deleteLater()

    reloader = HotReloader(engine, main_qml, ui_dir)
    # ──────────────────────────────────────────────────────────────────

    engine.load(os.fspath(main_qml))
    
    if not engine.rootObjects():
        logger.error("Failed to load QML.")
        sys.exit(-1)
        
    # Ensure session data is wiped on exit
    app.aboutToQuit.connect(folder_service.cleanup_data_directory)
        
    logger.info("Proximi started successfully.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
