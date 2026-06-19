"""Conftest for characterization/ingestion tests.

Mocks heavy optional dependencies (asyncpg, cocoindex, fastembed) that are
not present in the core test environment before test collection.
"""

import sys
from unittest.mock import MagicMock


_MOCKED_MODULES: list[str] = []


def _mock_if_absent(name: str, mock: MagicMock | None = None) -> None:
    if name not in sys.modules:
        sys.modules[name] = mock or MagicMock()
        _MOCKED_MODULES.append(name)


def pytest_configure(config: object) -> None:
    """Mock unavailable heavy deps before test collection."""
    # asyncpg — used by state_manager; not in core install
    asyncpg_mock = MagicMock()
    asyncpg_mock.Pool = MagicMock
    asyncpg_mock.Record = MagicMock
    _mock_if_absent("asyncpg", asyncpg_mock)

    # fastembed — pulled in by qdrant_writer indirectly
    fastembed_mock = MagicMock()
    fastembed_mock.SparseTextEmbedding = MagicMock()
    _mock_if_absent("fastembed", fastembed_mock)

    # cocoindex — optional ingestion framework
    cocoindex_mock = MagicMock()
    cocoindex_mock.flow_def = lambda _name: lambda fn: fn
    cocoindex_mock.sources = MagicMock()
    cocoindex_mock.targets = MagicMock()
    cocoindex_mock.functions = MagicMock()
    cocoindex_mock.VectorIndexDef = MagicMock
    cocoindex_mock.VectorSimilarityMetric = MagicMock()
    cocoindex_mock.auth_registry = MagicMock()
    cocoindex_mock.FlowLiveUpdaterOptions = MagicMock
    cocoindex_mock.FlowBuilder = MagicMock
    cocoindex_mock.DataScope = MagicMock
    cocoindex_mock.open_flow = MagicMock()
    cocoindex_mock.init = MagicMock()
    cocoindex_mock.setup_all_flows = MagicMock()
    cocoindex_mock.update_all_flows_async = MagicMock()
    cocoindex_mock.flow = MagicMock()
    cocoindex_mock.flow.flow_names = MagicMock(return_value=[])
    cocoindex_mock.flow.flow_by_name = MagicMock()
    cocoindex_mock.setting = MagicMock()
    cocoindex_mock.op = MagicMock()
    # function decorator: return the function unchanged
    cocoindex_mock.op.function = lambda fn: fn
    _mock_if_absent("cocoindex", cocoindex_mock)
    _mock_if_absent("cocoindex.flow", cocoindex_mock.flow)
    _mock_if_absent("cocoindex.op", cocoindex_mock.op)
    _mock_if_absent("cocoindex.setting", cocoindex_mock.setting)
    _mock_if_absent("cocoindex.sources", cocoindex_mock.sources)
    _mock_if_absent("cocoindex.targets", cocoindex_mock.targets)
    _mock_if_absent("cocoindex.functions", cocoindex_mock.functions)


def pytest_unconfigure(config: object) -> None:
    """Clean up mocked modules after tests."""
    for mod in _MOCKED_MODULES:
        sys.modules.pop(mod, None)
    _MOCKED_MODULES.clear()
