"""Apartment text and HTML card formatting utilities.

DRY: single source of truth extracted from property_card.py and apartment_tools.py.
"""

from __future__ import annotations


def format_apartment_text(results: list[dict]) -> str:
    """Format apartment search results for LLM context.

    Extracted from apartment_tools._format_apartment_results.

    Args:
        results: List of apartment dicts with 'payload' key.

    Returns:
        Formatted text listing apartments, or a "not found" message.
    """
    if not results:
        return "Апартаменты по вашим критериям не найдены. Попробуйте изменить параметры поиска."

    lines = []
    for i, apt in enumerate(results, 1):
        p = apt.get("payload", {})
        price_fmt = f"{p.get('price_eur', 0):,.0f}".replace(",", " ")
        view = ", ".join(p.get("view_tags", [])) or p.get("view_primary", "")
        furnished = "с мебелью" if p.get("is_furnished") else "без мебели"
        floor_str = "цоколь" if p.get("floor", 0) == 0 else f"{p.get('floor')} эт."

        lines.append(
            f"{i}. {p.get('complex_name', '?')}, секция {p.get('section', '?')}, "
            f"апп. {p.get('apartment_number', '?')} — "
            f"{p.get('rooms', '?')}к, {p.get('area_m2', '?')} м², {floor_str}, "
            f"вид: {view}, {price_fmt} €, {furnished}"
        )

    return f"Найдено {len(results)} апартаментов:\n" + "\n".join(lines)


def format_apartment_html(
    *,
    property_id: str,
    complex_name: str,
    location: str,
    property_type: str,
    floor: int,
    area_m2: int | float,
    view: str,
    price_eur: int | float,
    section: str = "",
    apartment_number: str = "",
) -> str:
    """Format apartment as a property card text.

    Extracted from property_card.format_property_card.

    Args:
        property_id: Apartment identifier (unused in text but part of interface).
        complex_name: Name of the residential complex.
        location: City or district.
        property_type: Type description (e.g. "1-спальня", "Студия").
        floor: Floor number (0 = ground/цоколь).
        area_m2: Area in square metres.
        view: View description.
        price_eur: Price in EUR.
        section: Optional building section.
        apartment_number: Optional apartment number.

    Returns:
        Formatted text card with emoji labels.
    """
    price_formatted = f"{int(price_eur):,}".replace(",", " ")
    lines = [f"🏠 Комплекс: {complex_name}"]
    if section:
        lines.append(f"🏗 Секция: {section}")
    if apartment_number:
        lines.append(f"🚪 №: {apartment_number}")
    if location:
        lines.append(f"📍 Город: {location}")
    if property_type:
        lines.append(f"🛏 Тип: {property_type}")
    if floor:
        lines.append(f"🔼 Этаж: {floor}")
    if area_m2:
        lines.append(f"📐 Площадь: {area_m2} м²")
    if view:
        lines.append(f"🌅 Вид: {view}")
    lines.append(f"💰 Цена: {price_formatted} €")
    return "\n".join(lines)
