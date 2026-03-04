"""Type-safe CallbackData factories for aiogram 3 (#785)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FeedbackCB(CallbackData, prefix="fb"):
    """Feedback like/dislike/done callback data."""

    action: str  # "like", "dislike", "done"
    trace_id: str = ""


class FeedbackReasonCB(CallbackData, prefix="fbr"):
    """Feedback dislike reason callback data."""

    code: str
    trace_id: str


class FavoriteCB(CallbackData, prefix="fav"):
    """Favorites add/remove/viewing callback data."""

    action: str  # "add", "remove", "viewing", "viewing_all"
    apartment_id: str = ""


class ResultsCB(CallbackData, prefix="results"):
    """Property results pagination callback data."""

    action: str  # "more", "refine", "viewing"


class ServiceCB(CallbackData, prefix="svc"):
    """Service menu callback data preserving svc:{value} format."""

    value: str


class CtaManagerCB(CallbackData, prefix="cta"):
    """CTA callback data for manager contact preserving cta:manager."""

    action: str


class CtaOfferCB(CallbackData, prefix="cta"):
    """CTA callback data for service offer preserving cta:get_offer:{service_key}."""

    action: str
    service_key: str


class ClearCacheCB(CallbackData, prefix="cc"):
    """Clear-cache callback data preserving cc:{tier} format."""

    tier: str


class HitlCB(CallbackData, prefix="hitl"):
    """HITL resume callback data preserving hitl:{action} format."""

    action: str


class CrmActionCB(CallbackData, prefix="crm"):
    """CRM quick-action callback data preserving crm:{entity}:{action}:{entity_id}."""

    entity: str
    action: str
    entity_id: int
