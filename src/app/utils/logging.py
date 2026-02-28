from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path("data/logs")
LOG_FILE = LOG_DIR / "app.log"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("job_application_assistant")
    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    root_logger = configure_logging()
    return root_logger if name is None else root_logger.getChild(name)
