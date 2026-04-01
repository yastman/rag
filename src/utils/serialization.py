"""Shared serialization helpers."""

import numpy as np


def convert_to_python_types(obj):
    """Convert numpy values into Python-native JSON-serializable types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: convert_to_python_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_python_types(item) for item in obj]
    return obj
