import numpy as np


class TemplateBase:
    """Base class for digitisation templates."""

    def __init__(self, labels: list[str], positions: np.ndarray, unit: str = "mm"):
        self.labels = list(labels)
        self.positions = np.asarray(positions)
        self.unit = unit

        # Fast label -> index lookup
        self.index = {l: i for i, l in enumerate(self.labels)}

    def get_chs_pos(self, labels: list[str] | str | None = None) -> np.ndarray:
        """Return channel positions for requested labels."""

        if labels is None:
            return self.positions

        if isinstance(labels, str):
            labels = [labels]

        idx = []
        for l in labels:
            if l not in self.index:
                print(f"Label '{l}' not found in template")
                continue
            idx.append(self.index[l])

        return self.positions[idx]
    
