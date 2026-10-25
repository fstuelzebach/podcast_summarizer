import logging
import os
from pathlib import Path


def setup_logging(level: int = logging.INFO) -> None:
    """Console logging, plus a file when LOG_FILE is set (cron / Task Scheduler)."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = os.getenv("LOG_FILE")
    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
