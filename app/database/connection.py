import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from app.utils.logger import logger
from app.database.base import Base
# Import models here so Base metadata is populated
import app.models

class DatabaseConnection:
    def __init__(self):
        self.db_path = Path("data/proximi.db")
        self.engine = None
        self.SessionLocal = None

    def initialize_database(self):
        """Creates the engine, session factory, and initializes the schema."""
        try:
            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # SQLite connection string
            sqlite_url = f"sqlite:///{self.db_path}"
            
            # Create engine
            self.engine = create_engine(
                sqlite_url, 
                connect_args={"check_same_thread": False},
                echo=False # Set to True for SQL logging
            )

            # Enable WAL mode for concurrent read/write from scan + face threads
            from sqlalchemy import event, text
            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()
            
            # Create session factory
            session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            self.SessionLocal = scoped_session(session_factory)
            
            # Create tables based on imported models
            Base.metadata.create_all(bind=self.engine)
            
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def clear_database(self):
        """Drops all tables and recreates them to start fresh."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database cleared and recreated successfully.")
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")

    def close_database(self):
        """Disposes the SQLAlchemy engine, releasing database file locks."""
        if self.SessionLocal:
            self.SessionLocal.remove()
        if self.engine:
            self.engine.dispose()
            self.engine = None
            logger.info("Database connection closed.")

db = DatabaseConnection()
