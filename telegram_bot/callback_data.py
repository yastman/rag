"""Type-safe CallbackData factories for aiogram 3 (#785)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FeedbackCB(CallbackData, prefix="fb"):  # type: ignore[call-arg]  # aiogram CallbackData accepts prefix at runtime
    """Feedback like/dislike/done callback data."""

    action: str  # "like", "dislike", "done"
    trace_id: str = ""


class FeedbackReasonCB(CallbackData, prefix="fbr"):  # type: ignore[call-arg]  # aiogram CallbackData accepts prefix at runtime
    """Feedback dislike reason callback data."""

    code: str
    trace_id: str


class FavoriteCB(CallbackData, prefix="fav"):  # type: ignore[call-arg]  # aiogram CallbackData accepts prefix at runtime
    """Favorites add/remove/viewing callback data."""

    action: str  # "add", "remove", "viewing", "viewing_all"
    apartment_id: str = ""


class ResultsCB(CallbackData, prefix="results"):  # type: ignore[call-arg]  # aiogram CallbackData accepts prefix at runtime
    """Property results pagination callback data."""

    action: str  # "more", "refine", "viewing"


class DemoCB(CallbackData, prefix="demo"):  # type: ignore[call-arg]  # aiogram CallbackData accepts prefix at runtime
    """Demo flow callback data."""

    action: str  # "apartments", "example"
    idx: int = 0
