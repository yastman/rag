"""Manager menu rendering for /start command (#388)."""

from __future__ import annotations


def render_start_menu(*, role: str, domain: str) -> str:
    """Render /start menu text based on user role."""
    if role == "manager":
        return f"Manager menu ({domain})\n- /leads\n- /history <query>\n- /stats\n- /help"
    return f"Hi! I am your assistant for {domain}.\nAsk questions in free text or use /help."
