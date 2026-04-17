from __future__ import annotations

import json
from pathlib import Path


_SETTINGS_FILE_NAME = "default_settings.json"
_BUNDLED_SETTINGS_PATH = Path(__file__).with_name(_SETTINGS_FILE_NAME)


def bundled_settings_path() -> Path:
    return _BUNDLED_SETTINGS_PATH


def default_user_settings_path() -> Path:
    return Path.home() / ".pylhemus" / _SETTINGS_FILE_NAME


def resolve_settings_path(settings_path: Path | None = None) -> Path:
    if settings_path is not None:
        target = Path(settings_path)
        if not target.exists():
            _initialise_settings_file(target)
        return target

    project_settings = Path.cwd() / _SETTINGS_FILE_NAME
    if project_settings.exists():
        return project_settings

    user_settings = default_user_settings_path()
    if not user_settings.exists():
        _initialise_settings_file(user_settings)
    return user_settings


def load_settings(settings_path: Path | None = None) -> dict:
    path = resolve_settings_path(settings_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _initialise_settings_file(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_BUNDLED_SETTINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")