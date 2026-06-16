from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PACKAGE_DEFAULTS = Path(__file__).with_name("default_settings.json")
USER_DIR = Path.home() / ".pylhemus"
USER_SETTINGS = USER_DIR / "settings.json"
LEGACY_USER_SETTINGS = USER_DIR / "default_settings.json"
PROJECT_SETTINGS = Path.cwd() / "pylhemus.settings.json"


def _load_json_if_exists(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _deep_merge(base: dict, *overrides: dict) -> dict:
    result: dict[str, Any] = json.loads(json.dumps(base))

    for override in overrides:
        for k, v in override.items():
            if (
                k in result
                and isinstance(result[k], dict)
                and isinstance(v, dict)
            ):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v

    return result


def _migrate_legacy_user_settings():
    if LEGACY_USER_SETTINGS.exists() and not USER_SETTINGS.exists():
        USER_DIR.mkdir(parents=True, exist_ok=True)
        LEGACY_USER_SETTINGS.rename(USER_SETTINGS)


def load_settings() -> dict:
    """Load layered pylhemus settings.

    Order: defaults -> user -> project
    """

    _migrate_legacy_user_settings()

    defaults = _load_json_if_exists(PACKAGE_DEFAULTS)
    user = _load_json_if_exists(USER_SETTINGS)
    project = _load_json_if_exists(PROJECT_SETTINGS)

    return _deep_merge(defaults, user, project)


def user_settings_path() -> Path:
    """Return path to the user settings file (~/.pylhemus/settings.json)."""
    return USER_SETTINGS


def load_user_settings() -> dict:
    """Load only the user settings layer."""

    _migrate_legacy_user_settings()

    if not USER_DIR.exists():
        USER_DIR.mkdir(parents=True, exist_ok=True)

    return _load_json_if_exists(USER_SETTINGS)


def settings_sources() -> dict[str, Path | None]:
    """Return paths of active settings layers for GUI display."""

    return {
        "defaults": PACKAGE_DEFAULTS if PACKAGE_DEFAULTS.exists() else None,
        "user": USER_SETTINGS if USER_SETTINGS.exists() else None,
        "project": PROJECT_SETTINGS if PROJECT_SETTINGS.exists() else None,
    }
