"""ML-based prompt injection scanner using llm-guard.

Lazy-loads ProtectAI/deberta-v3-base-prompt-injection-v2 on first call.
Gracefully degrades when llm-guard is not installed (returns safe defaults).

Enable: GUARD_ML_ENABLED=true + `uv sync --extra guard-ml`
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)

# Lazy singleton — model loaded on first scan, not at import
_scanner_instance: Any | None = None


def _get_scanner() -> Any:
    """Get or create the PromptInjection scanner singleton.

    Raises ImportError if llm-guard is not installed.
    """
    global _scanner_instance

    if _scanner_instance is not None:
        return _scanner_instance

    from llm_guard.input_scanners import PromptInjection
    from llm_guard.input_scanners.prompt_injection import MatchType

    logger.info("Loading llm-guard PromptInjection scanner (first call, lazy init)...")
    _scanner_instance = PromptInjection(threshold=0.5, match_type=MatchType.FULL)
    logger.info("llm-guard PromptInjection scanner loaded successfully")
    return _scanner_instance


def scan_prompt_injection(text: str) -> tuple[bool, float]:
    """Scan text for prompt injection using ML classifier.

    Returns:
        (detected, risk_score) — detected=True if injection found,
        risk_score is 0.0-1.0 confidence.
        On error: returns (False, 0.0) — fail-open to avoid blocking users.
    """
    try:
        scanner = _get_scanner()
        _sanitized, is_valid, risk_score = scanner.scan(text)
        detected = not is_valid
        return (detected, float(risk_score))
    except ImportError:
        logger.warning("llm-guard not installed — ML guard layer skipped")
        return (False, 0.0)
    except Exception:
        logger.exception("ML guard scanner error — returning safe defaults")
        return (False, 0.0)
