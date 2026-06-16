import numpy as np
from mne.channels import get_builtin_montages, make_standard_montage

from .template_base import TemplateBase


class EEGcapTemplate(TemplateBase):
    """EEG template backed by an MNE montage."""

    def __init__(self, montage_name: str):
        if montage_name not in get_builtin_montages():
            raise ValueError(f"Montage '{montage_name}' is not a standard montage.")

        montage = make_standard_montage(montage_name)
        pos = montage.get_positions()["ch_pos"]

        labels = list(pos.keys())
        positions = np.array(list(pos.values()))

        self.montage_name = montage_name
        self.montage = montage

        super().__init__(labels=labels, positions=positions, unit="mm")

    def get_montage_information(self):
        pos = self.montage.get_positions()["ch_pos"]
        return pos, self.montage.ch_names, "mm"
