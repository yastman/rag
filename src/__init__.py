"""Contextual RAG Pipeline package metadata.

Keep this module lightweight.
Heavy imports here can block CLI startup (e.g. ``python -m src.ingestion.unified.cli``),
because Python imports ``src`` before the target submodule.
"""

__version__ = "2.3.1"
__author__ = "Contextual RAG Team"
