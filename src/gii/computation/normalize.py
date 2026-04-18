"""Normalization functions for sub-index scores."""

import numpy as np


def zscore_normalize(values: list[float]) -> list[float]:
    """Z-score normalize a list of values. Returns 0s if std is 0."""
    arr = np.array(values, dtype=float)
    mean = np.mean(arr)
    std = np.std(arr)
    if std == 0:
        return [0.0] * len(values)
    return ((arr - mean) / std).tolist()


def minmax_rescale(values: list[float], floor: float = 0, ceiling: float = 100) -> list[float]:
    """Rescale values to [floor, ceiling] range."""
    arr = np.array(values, dtype=float)
    vmin, vmax = np.min(arr), np.max(arr)
    if vmin == vmax:
        mid = (floor + ceiling) / 2
        return [mid] * len(values)
    scaled = (arr - vmin) / (vmax - vmin) * (ceiling - floor) + floor
    return scaled.tolist()


def normalize_to_0_100(values: list[float]) -> list[float]:
    """Two-step normalization: z-score then min-max to 0-100."""
    z = zscore_normalize(values)
    return minmax_rescale(z)
