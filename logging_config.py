"""Shared logging setup.

Writes to both the console (so the terminal still shows live output,
same as before) and a rotating log file under logs/app.log, so backend
activity — investigations especially — can be reviewed after the fact
instead of only being visible in whatever terminal uvicorn happens to be
running in.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with console + rotating file output.

    Safe to call more than once (e.g. across uvicorn --reload restarts) —
    replaces any handlers this already added instead of stacking more on.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [file_handler, console_handler]
