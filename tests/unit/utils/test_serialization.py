"""Unit tests for shared serialization helpers."""

import numpy as np
import pytest

from src.utils.serialization import convert_to_python_types


def test_convert_nested_numpy_values_to_python_types() -> None:
    payload = {
        "dense": np.array([1.0, 2.0]),
        "score": np.float32(0.95),
        "count": np.int64(3),
    }

    result = convert_to_python_types(payload)

    assert result == {"dense": [1.0, 2.0], "score": pytest.approx(0.95), "count": 3}
