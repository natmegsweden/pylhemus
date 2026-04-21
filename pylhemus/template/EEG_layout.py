import mne
import numpy as np
from .template_base import TemplateBase
from mne.channels import get_builtin_montages, make_standard_montage

class EEGcapTemplate(TemplateBase):
    def __init__(self, montage_name: str):
        if montage_name not in get_builtin_montages():
            raise ValueError(f"Montage '{montage_name}' is not a standard montage.")
        self.montage = make_standard_montage(montage_name)

    def get_montage_information(self):

        positions = self.montage.get_positions()['ch_pos']

        return positions, self.montage.ch_names, "mm"