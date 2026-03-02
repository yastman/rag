"""Kommo CRM seeder — populate CRM with realistic demo data from Qdrant apartments.

Usage:
    python -m scripts.kommo_seed --dry-run --contacts 30 --leads 50
    python -m scripts.kommo_seed --contacts 30 --leads 50
    python -m scripts.kommo_seed --contacts 30 --leads 50 --pipeline-id 12345
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Seed Kommo CRM with demo data")
    parser.add_argument("--contacts", type=int, default=30, help="Number of contacts (default: 30)")
    parser.add_argument("--leads", type=int, default=50, help="Number of leads/deals (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without API calls")
    parser.add_argument("--pipeline-id", type=int, default=None, help="Kommo pipeline ID override")
    return parser.parse_args(argv)


# --- Data pools ---

FIRST_NAMES_RU = [
    "Александр",
    "Андрей",
    "Дмитрий",
    "Сергей",
    "Максим",
    "Иван",
    "Артём",
    "Николай",
    "Михаил",
    "Евгений",
    "Алексей",
    "Роман",
    "Владимир",
    "Олег",
    "Виктор",
    "Анна",
    "Мария",
    "Елена",
    "Ольга",
    "Наталья",
    "Ирина",
    "Светлана",
    "Татьяна",
    "Екатерина",
    "Юлия",
    "Марина",
    "Виктория",
    "Дарья",
    "Алина",
    "Кристина",
]

LAST_NAMES_RU = [
    "Иванов",
    "Петров",
    "Сидоров",
    "Козлов",
    "Новиков",
    "Морозов",
    "Волков",
    "Соколов",
    "Кузнецов",
    "Попов",
    "Лебедев",
    "Семёнов",
    "Павлов",
    "Голубев",
    "Виноградов",
    "Богданов",
    "Воробьёв",
    "Фёдоров",
    "Тарасов",
    "Белов",
]

FIRST_NAMES_UA = [
    "Олександр",
    "Тарас",
    "Богдан",
    "Василь",
    "Ярослав",
    "Степан",
    "Остап",
    "Оксана",
    "Леся",
    "Наталія",
    "Ганна",
    "Софія",
    "Катерина",
    "Дарина",
]

LAST_NAMES_UA = [
    "Коваленко",
    "Бондаренко",
    "Шевченко",
    "Мельник",
    "Бойко",
    "Ткаченко",
    "Кравченко",
    "Олійник",
    "Лисенко",
    "Гончаренко",
    "Савченко",
    "Руденко",
]

PHONE_PREFIXES = ["+380", "+7", "+359", "+48", "+49"]


def generate_contact_data(index: int) -> dict:
    """Generate a contact dict with realistic RU/UA data."""
    if index % 3 == 0:  # ~33% Ukrainian names
        first = random.choice(FIRST_NAMES_UA)
        last = random.choice(LAST_NAMES_UA)
    else:
        first = random.choice(FIRST_NAMES_RU)
        last = random.choice(LAST_NAMES_RU)

    prefix = random.choice(PHONE_PREFIXES)
    number = "".join([str(random.randint(0, 9)) for _ in range(9)])
    phone = f"{prefix}{number}"

    return {"first_name": first, "last_name": last, "phone": phone}


@dataclass(frozen=True)
class Scenario:
    """CRM deal scenario template."""

    service_key: str
    crm_title: str
    note_templates: list[str]
    task_templates: list[str]


SCENARIOS = [
    Scenario(
        service_key="apartment_search",
        crm_title="Подбор апартаментов",
        note_templates=[
            "Клиент интересуется {complex_name}. Бюджет: {budget}€. Источник: Telegram бот.",
            "Подобраны варианты: {complex_name}, {rooms}-комн, {area_m2}м², этаж {floor}. Вид: {view_primary}.",
            "Клиент запросил планировку и фото для {complex_name} #{apartment_number}.",
        ],
        task_templates=[
            "Перезвонить: {phone} ({name}) — подбор апартаментов в {complex_name}",
            "Отправить подборку {rooms}-комн в {complex_name} на почту",
        ],
    ),
    Scenario(
        service_key="viewing",
        crm_title="Осмотр объектов",
        note_templates=[
            "Запись на осмотр: {complex_name}. Дата: согласовать. Контакт: {phone}.",
            "Клиент хочет посмотреть {rooms}-комн в {complex_name}, этаж {floor}.",
        ],
        task_templates=[
            "Согласовать дату осмотра с {name} — {complex_name}",
            "Подготовить ключи для осмотра {complex_name} #{apartment_number}",
        ],
    ),
    Scenario(
        service_key="infotour",
        crm_title="Инфотур",
        note_templates=[
            "Заявка на инфотур. Контакт: {phone}. Предпочтения: {complex_name}, {view_primary}.",
            "Инфотур запланирован. Интерес к {rooms}-комн в ценовом диапазоне до {budget}€.",
        ],
        task_templates=[
            "Перезвонить: {phone} ({name}) — бронирование инфотура",
            "Отправить программу инфотура для {name}",
        ],
    ),
    Scenario(
        service_key="installment",
        crm_title="Рассрочка",
        note_templates=[
            "Запрос рассрочки на {complex_name} #{apartment_number}. Цена: {price_eur}€. Источник: Telegram.",
            "Расчёт рассрочки: {price_eur}€, взнос 10% = {deposit}€, ежемесячно ~{monthly}€ на 36 мес.",
        ],
        task_templates=[
            "Отправить расчёт рассрочки для {complex_name} — {name}",
            "Подготовить договор рассрочки для {name}",
        ],
    ),
    Scenario(
        service_key="vnzh",
        crm_title="ВНЖ и легализация",
        note_templates=[
            "Запрос по ВНЖ в Болгарии. Контакт: {phone}. Планирует покупку в {complex_name}.",
            "Консультация по ВНЖ проведена. Клиент рассматривает {complex_name} как основу для ВНЖ.",
        ],
        task_templates=[
            "Перезвонить: {phone} ({name}) — консультация по ВНЖ",
            "Отправить список документов для ВНЖ — {name}",
        ],
    ),
    Scenario(
        service_key="passive_income",
        crm_title="Пассивный доход",
        note_templates=[
            "Интерес к сдаче в аренду. Объект: {complex_name} #{apartment_number}, {rooms}-комн, {area_m2}м².",
            "Расчёт доходности для {complex_name}: ~{rental_yield}€/мес при ставке аренды сезона.",
        ],
        task_templates=[
            "Отправить расчёт доходности {complex_name} — {name}",
            "Перезвонить: {phone} ({name}) — условия управления",
        ],
    ),
]


def pick_scenario() -> Scenario:
    """Pick a random scenario."""
    return random.choice(SCENARIOS)


# --- Qdrant reader ---


def fetch_apartments(
    qdrant_client: object,
    collection: str = "apartments",
    limit: int = 50,
) -> list[dict]:
    """Scroll apartments from Qdrant (sync, no vectors)."""
    records, _ = qdrant_client.scroll(  # type: ignore[attr-defined]
        collection_name=collection,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    apartments = []
    for r in records:
        if r.payload:
            apartments.append(dict(r.payload))
    logger.info("Fetched %d apartments from Qdrant collection '%s'", len(apartments), collection)
    return apartments


# --- Lead distribution ---

STAGE_WEIGHTS = {
    "new": 0.30,
    "qualified": 0.25,
    "negotiation": 0.20,
    "proposal": 0.15,
    "won": 0.05,
    "lost": 0.05,
}


def distribute_statuses(count: int, statuses: dict[str, int]) -> list[int]:
    """Distribute leads across funnel stages by weight.

    Args:
        count: Total number of leads.
        statuses: Mapping of stage_name → status_id.

    Returns:
        List of status_ids, length == count.
    """
    result: list[int] = []
    for stage, weight in STAGE_WEIGHTS.items():
        if stage in statuses:
            n = round(count * weight)
            result.extend([statuses[stage]] * n)
    # Pad/trim to exact count
    while len(result) < count:
        result.append(statuses.get("new", next(iter(statuses.values()))))
    return result[:count]


def build_lead_data(
    scenario: Scenario,
    apartment: dict,
    contact_name: str,
    status_id: int,
    pipeline_id: int | None,
) -> dict:
    """Build a dict suitable for LeadCreate."""
    price_eur = apartment.get("price_eur", 0)
    complex_name = apartment.get("complex_name", "N/A")
    return {
        "name": f"{scenario.crm_title} {complex_name} — {contact_name}",
        "budget": int(price_eur * 100),  # Kommo uses cents
        "pipeline_id": pipeline_id,
        "status_id": status_id,
    }


# --- Template rendering ---


def _build_render_context(apartment: dict, extra: dict) -> dict:
    """Merge apartment payload + extra context for template rendering."""
    price_eur = apartment.get("price_eur", 0)
    deposit = int(price_eur * 0.10)
    monthly = int((price_eur - deposit) / 36) if price_eur else 0
    rental_yield = int(price_eur * 0.005)  # rough estimate ~0.5%/month
    return {
        **apartment,
        **extra,
        "budget": extra.get("budget", price_eur),
        "deposit": deposit,
        "monthly": monthly,
        "rental_yield": rental_yield,
    }


def _extract_keys(template: str) -> list[str]:
    """Extract {key} placeholders from a template string."""
    return re.findall(r"\{(\w+)\}", template)


def render_note(template: str, apartment: dict, ctx: dict) -> str:
    """Render note template with apartment + context data. Safe: ignores missing keys."""
    merged = _build_render_context(apartment, ctx)
    try:
        return template.format_map(merged)
    except KeyError:
        return template.format_map({**merged, **dict.fromkeys(_extract_keys(template), "N/A")})


def render_task(template: str, apartment: dict, ctx: dict) -> str:
    """Render task template (same logic as notes)."""
    return render_note(template, apartment, ctx)


# --- Seeding orchestrator ---


@dataclass
class SeedStats:
    """Seeding statistics."""

    contacts_created: int = 0
    leads_created: int = 0
    notes_created: int = 0
    tasks_created: int = 0
    links_created: int = 0
    api_calls: int = 0
    errors: int = 0


async def seed_crm(
    *,
    kommo_client: object | None,
    apartments: list[dict],
    statuses: dict[str, int],
    pipeline_id: int | None,
    num_contacts: int = 30,
    num_leads: int = 50,
    dry_run: bool = False,
    semaphore_limit: int = 5,
) -> dict:
    """Main seeding orchestrator.

    Returns:
        Stats dict with counts of created entities.
    """
    stats = SeedStats()
    sem = asyncio.Semaphore(semaphore_limit)

    # --- Phase 1: Create contacts ---
    contacts: list[dict] = []
    for i in range(num_contacts):
        data = generate_contact_data(i)
        if dry_run:
            contacts.append({"id": 1000 + i, **data})
            stats.contacts_created += 1
            logger.info(
                "[DRY-RUN] Contact: %s %s (%s)",
                data["first_name"],
                data["last_name"],
                data["phone"],
            )
        else:
            async with sem:
                from telegram_bot.services.kommo_models import ContactCreate

                contact = await kommo_client.upsert_contact(  # type: ignore[union-attr]
                    data["phone"],
                    ContactCreate(
                        first_name=data["first_name"],
                        last_name=data["last_name"],
                        phone=data["phone"],
                    ),
                )
                contacts.append({"id": contact.id, **data})
                stats.contacts_created += 1
                stats.api_calls += 1
                logger.info(
                    "Created contact #%d: %s %s", contact.id, data["first_name"], data["last_name"]
                )

    # --- Phase 2: Create leads + link + notes + tasks ---
    status_ids = distribute_statuses(num_leads, statuses)
    random.shuffle(status_ids)

    for i in range(num_leads):
        scenario = pick_scenario()
        apartment = random.choice(apartments)
        contact = contacts[i % len(contacts)]
        status_id = status_ids[i]
        contact_name = f"{contact['last_name']} {contact['first_name'][0]}."

        lead_data = build_lead_data(scenario, apartment, contact_name, status_id, pipeline_id)
        render_ctx = {
            "phone": contact["phone"],
            "name": contact_name,
            "budget": apartment.get("price_eur", 0),
        }

        if dry_run:
            stats.leads_created += 1
            logger.info("[DRY-RUN] Lead: %s (status=%d)", lead_data["name"], status_id)

            # Notes
            note_count = random.randint(1, min(3, len(scenario.note_templates)))
            for tmpl in scenario.note_templates[:note_count]:
                note_text = render_note(tmpl, apartment, render_ctx)
                stats.notes_created += 1
                logger.info("[DRY-RUN]   Note: %s", note_text[:80])

            # Tasks (only for non-closed leads)
            is_closed = status_id in (statuses.get("won", -1), statuses.get("lost", -1))
            if not is_closed and scenario.task_templates:
                task_text = render_task(scenario.task_templates[0], apartment, render_ctx)
                stats.tasks_created += 1
                logger.info("[DRY-RUN]   Task: %s", task_text[:80])

            stats.links_created += 1
        else:
            async with sem:
                from telegram_bot.services.kommo_models import LeadCreate, TaskCreate

                lead = await kommo_client.create_lead(  # type: ignore[union-attr]
                    LeadCreate(**lead_data)
                )
                lead_id = lead.id
                stats.leads_created += 1
                stats.api_calls += 1

            # Link contact
            async with sem:
                await kommo_client.link_contact_to_lead(lead_id, contact["id"])  # type: ignore[union-attr]
                stats.links_created += 1
                stats.api_calls += 1

            # Notes
            note_count = random.randint(1, min(3, len(scenario.note_templates)))
            for tmpl in scenario.note_templates[:note_count]:
                note_text = render_note(tmpl, apartment, render_ctx)
                async with sem:
                    await kommo_client.add_note("leads", lead_id, note_text)  # type: ignore[union-attr]
                    stats.notes_created += 1
                    stats.api_calls += 1

            # Tasks (non-closed only)
            is_closed = status_id in (statuses.get("won", -1), statuses.get("lost", -1))
            if not is_closed and scenario.task_templates:
                task_text = render_task(scenario.task_templates[0], apartment, render_ctx)
                # Due date: 1-7 days from now; 20% overdue (past)
                if random.random() < 0.2:
                    due = int(time.time()) - random.randint(1, 3) * 86400
                else:
                    due = int(time.time()) + random.randint(1, 7) * 86400
                async with sem:
                    await kommo_client.create_task(  # type: ignore[union-attr]
                        TaskCreate(text=task_text, entity_id=lead_id, complete_till=due)
                    )
                    stats.tasks_created += 1
                    stats.api_calls += 1

            logger.info("Created lead #%d: %s", lead_id, lead_data["name"])

    return {
        "contacts_created": stats.contacts_created,
        "leads_created": stats.leads_created,
        "notes_created": stats.notes_created,
        "tasks_created": stats.tasks_created,
        "links_created": stats.links_created,
        "api_calls": stats.api_calls,
        "errors": stats.errors,
    }


async def main() -> None:
    """CLI entrypoint: parse args, connect services, run seeder."""
    args = parse_args()

    # --- Connect to Qdrant (sync) ---
    from qdrant_client import QdrantClient

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant = QdrantClient(url=qdrant_url)
    apartments = fetch_apartments(qdrant, collection="apartments", limit=50)
    if not apartments:
        logger.error("No apartments found in Qdrant. Run ingestion first.")
        sys.exit(1)
    random.shuffle(apartments)

    # --- Pipeline statuses ---
    statuses: dict[str, int] = {
        "new": 0,
        "qualified": 0,
        "negotiation": 0,
        "proposal": 0,
        "won": 142,
        "lost": 143,
    }
    pipeline_id = args.pipeline_id

    kommo = None
    redis_client = None

    if not args.dry_run:
        import redis.asyncio as aioredis

        from telegram_bot.services.kommo_client import KommoClient
        from telegram_bot.services.kommo_token_store import KommoTokenStore

        redis_password = os.environ.get("REDIS_PASSWORD", "")
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
        redis_client = aioredis.from_url(redis_url, decode_responses=False)

        subdomain = os.environ.get("KOMMO_SUBDOMAIN", "")
        if not subdomain:
            logger.error("KOMMO_SUBDOMAIN not set. Cannot connect to Kommo API.")
            sys.exit(1)

        token_store = KommoTokenStore(
            redis=redis_client,
            subdomain=subdomain,
            client_id=os.environ.get("KOMMO_CLIENT_ID", ""),
            client_secret=os.environ.get("KOMMO_CLIENT_SECRET", ""),
            redirect_uri=os.environ.get("KOMMO_REDIRECT_URI", ""),
        )
        kommo = KommoClient(subdomain=subdomain, token_store=token_store)

        if not pipeline_id:
            pipeline_id = int(os.environ.get("KOMMO_DEFAULT_PIPELINE_ID", "0")) or None

        if pipeline_id:
            try:
                pipelines = await kommo.list_pipelines()
                logger.info("Found %d pipelines in Kommo", len(pipelines))
            except Exception:
                logger.warning("Could not fetch pipelines, using defaults")

    logger.info(
        "Starting seed: %d contacts, %d leads, pipeline=%s, dry_run=%s",
        args.contacts,
        args.leads,
        pipeline_id,
        args.dry_run,
    )
    logger.info("Apartment pool: %d objects", len(apartments))

    result = await seed_crm(
        kommo_client=kommo,
        apartments=apartments,
        statuses=statuses,
        pipeline_id=pipeline_id,
        num_contacts=args.contacts,
        num_leads=args.leads,
        dry_run=args.dry_run,
    )

    logger.info("=== Seeding complete ===")
    logger.info("Contacts: %d", result["contacts_created"])
    logger.info("Leads:    %d", result["leads_created"])
    logger.info("Notes:    %d", result["notes_created"])
    logger.info("Tasks:    %d", result["tasks_created"])
    logger.info("Links:    %d", result["links_created"])
    logger.info("API calls: %d", result["api_calls"])
    if result["errors"]:
        logger.warning("Errors: %d", result["errors"])

    if kommo:
        await kommo.close()
    if redis_client:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
