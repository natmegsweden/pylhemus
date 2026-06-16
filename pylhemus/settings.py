from __future__ import annotations

# Backwards compatibility wrapper around the new layered loader.

from .settings_loader import load_settings  # re-export

__all__ = ["load_settings"]
