import logging
import uuid


def generate_id(prefix=""):
    """Generate a unique 12-char hex ID, optionally with a prefix."""
    uid = uuid.uuid4().hex[:12]
    return "{}{}".format(prefix, uid) if prefix else uid


def setup_logging(level="info"):
    """Configure root logging. Accepts debug/info/warning/warn/error."""
    level_name = level.upper()
    if level_name == "WARN":
        level_name = "WARNING"
    numeric_level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger().setLevel(numeric_level)
