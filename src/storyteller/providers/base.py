from __future__ import annotations


class BaseProvider:
    """Common base for all providers. Holds a reference to the Config."""

    def __init__(self, config):
        self.config = config

    def _validate_config(self):
        """Hook for subclasses to validate their config. No-op by default."""
        return None
