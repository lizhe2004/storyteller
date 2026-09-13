import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import uuid


def generate_id(prefix=""):
    """Generate a unique 12-char hex ID, optionally with a prefix."""
    uid = uuid.uuid4().hex[:12]
    return "{}{}".format(prefix, uid) if prefix else uid


_CONSOLE_MARKER = "_storyteller_console_handler"
_FILE_MARKER = "_storyteller_file_handler"


def setup_logging(level="info", log_dir=None):
    """Configure readable console and optional rotating file logging."""
    level_name = level.upper()
    if level_name == "WARN":
        level_name = "WARNING"
    numeric_level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console = next(
        (h for h in root.handlers if getattr(h, _CONSOLE_MARKER, False)),
        None,
    )
    if console is None:
        console = logging.StreamHandler(sys.stderr)
        setattr(console, _CONSOLE_MARKER, True)
        root.addHandler(console)
    console.setLevel(numeric_level)
    console.setFormatter(formatter)

    if log_dir is not None:
        path = Path(log_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
            target = path / "storyteller.log"
            file_handler = next(
                (h for h in root.handlers if getattr(h, _FILE_MARKER, False)),
                None,
            )
            current = getattr(file_handler, "baseFilename", None) if file_handler else None
            if file_handler is None or Path(current) != target.resolve():
                if file_handler is not None:
                    root.removeHandler(file_handler)
                    file_handler.close()
                file_handler = RotatingFileHandler(
                    target, maxBytes=5 * 1024 * 1024, backupCount=3,
                    encoding="utf-8",
                )
                setattr(file_handler, _FILE_MARKER, True)
                root.addHandler(file_handler)
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
        except OSError:
            # Logging must never prevent story generation.
            logging.getLogger(__name__).warning(
                "event=file_logging_unavailable log_dir=%s", path
            )
