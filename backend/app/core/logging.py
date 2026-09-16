import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging() -> None:
    """Setup logging with console and file handlers with rotation."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

    # Console handler (to stderr)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))

    # File handler with rotation (max 10MB per file, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_dir / "anvero.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))

    # Security logger file handler (separate log for security events)
    security_logger = logging.getLogger("security")
    security_handler = RotatingFileHandler(
        log_dir / "security.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=10,
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(logging.Formatter(log_format))
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)
