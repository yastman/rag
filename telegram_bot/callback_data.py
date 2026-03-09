"""Type-safe CallbackData factories for aiogram 3 (***REMOVED***785)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FeedbackCB(CallbackData, prefix="fb"):
    """Feedback like/dislike/done callback data."""

    action: str  ***REMOVED*** "like", "dislike", "done"
    trace_id: str = ""


class FeedbackReasonCB(CallbackData, prefix="fbr"):
    """Feedback dislike reason callback data."""

    code: str
    trace_id: str


class FavoriteCB(CallbackData, prefix="fav"):
    """Favorites add/remove/viewing callback data."""

    action: str  ***REMOVED*** "add", "remove", "viewing", "viewing_all"
    apartment_id: str = ""


class ResultsCB(CallbackData, prefix="results"):
    """Property results pagination callback data."""

    action: str  ***REMOVED*** "more", "refine", "viewing"


class DemoCB(CallbackData, prefix="demo"):
    """Demo flow callback data."""

    action: str  ***REMOVED*** "apartments", "example"
    idx: int = 0


class FilterPanelCB(CallbackData, prefix="fpanel"):
    """Filter panel callback data."""

    action: str  ***REMOVED*** "select", "apply", "reset", "back", "set"
    field: str  ***REMOVED*** "city", "rooms", "budget", "view", "area", "floor", "complex", "furnished", "promotion"
    value: str = ""  ***REMOVED*** значение при action="set"
