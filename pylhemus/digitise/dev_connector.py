from __future__ import annotations

import math
import random

import numpy as np


class DevModeConnector:
    """Mock FASTRAK connector for development/testing without hardware."""

    def __init__(self, normal_radius_cm: float = 15.0, faulty_radius_cm: float = 50.0):
        self.normal_radius = normal_radius_cm
        self.faulty_radius = faulty_radius_cm
        self.serialobj = None
        self.n_receivers = 2
        self.data_length = 47
        self._injected_position: tuple[float, float, float] | None = None
        self._use_faulty = False

    def prepare_for_digitisation(self) -> None:
        pass

    def clear_old_data(self) -> None:
        pass

    def inject_point(self, faulty: bool = False) -> tuple[float, float, float]:
        """Generate and inject a random point on a sphere."""
        self._use_faulty = faulty
        self._injected_position = self._random_spherical_point(
            self.faulty_radius if faulty else self.normal_radius
        )
        return self._injected_position

    def _random_spherical_point(self, radius: float) -> tuple[float, float, float]:
        theta = random.uniform(0, 2 * math.pi)
        phi = random.uniform(0, math.pi)
        x = radius * math.sin(phi) * math.cos(theta)
        y = radius * math.sin(phi) * math.sin(theta)
        z = radius * math.cos(phi)
        return (x, y, z)

    def get_position_relative_to_head_receiver(self):
        if self._injected_position is not None:
            position = self._injected_position
            self._injected_position = None
        else:
            position = self._random_spherical_point(
                self.faulty_radius if self._use_faulty else self.normal_radius
            )

        sensor_data = np.zeros((7, self.n_receivers))
        sensor_data[1, 0] = position[0]
        sensor_data[2, 0] = position[1]
        sensor_data[3, 0] = position[2]
        sensor_data[1, 1] = 0.0
        sensor_data[2, 1] = 0.0
        sensor_data[3, 1] = 0.0

        return sensor_data, position