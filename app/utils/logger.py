import logging
import os
import sys
from pathlib import Path

def setup_logger() -> logging.Logger:
    """Configures application-wide logging."""
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / "proximi.log"
    
    logger = logging.getLogger("proximi")
    logger.setLevel(logging.DEBUG)
    
    # Prevent adding handlers multiple times if imported multiple times
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    return logger

def shutdown_logger():
    """Closes all handlers to release file locks."""
    global logger
    handlers = logger.handlers[:]
    for handler in handlers:
        handler.close()
        logger.removeHandler(handler)

logger = setup_logger()
