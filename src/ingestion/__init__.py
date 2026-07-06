"""Document ingestion package.

Use lazy exports to keep imports cheap for unified CLI and other lightweight tools.

CocoIndex has been removed (#2834). The FlowConfig, check_cocoindex_available,
and create_document_flow exports have been removed.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any


__all__: list[str] = []


if TYPE_CHECKING:
    pass


_LAZY_ATTRS: dict[str, tuple[str, str]] = {}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is not None:
        module_name, attr_name = target
        module = import_module(module_name, package=__name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module 'src.ingestion' has no attribute '{name}'")
