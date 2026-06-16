"""Template registry for pylhemus digitisation templates."""

from mne.channels import get_builtin_montages

from .EEG_layout import EEGcapTemplate


# Build registry dynamically from MNE montages
TEMPLATES = {
    name: (lambda n=name: EEGcapTemplate(n)) for name in get_builtin_montages()
}


def list_templates() -> list[str]:
    """Return available template names."""
    return sorted(TEMPLATES.keys())


def create_template(name: str):
    """Instantiate a template by name."""
    if name not in TEMPLATES:
        raise KeyError(f"Template '{name}' not found in registry.")
    return TEMPLATES[name]()
