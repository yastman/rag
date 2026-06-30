"""Re-export from canonical engine module.

The engine owns prompt management; this shim keeps legacy import paths working.
"""

from src.runtime.integrations.prompt_manager import (  # noqa: F401
    _apply_fallback_vars,
    _reset_client,
    get_prompt,
    get_prompt_with_config,
    get_prompt_with_object,
)
