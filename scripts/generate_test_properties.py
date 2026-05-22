#!/usr/bin/env python3
"""Generate test property data for E2E testing."""

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


# Bulgarian property complexes (realistic names)
COMPLEXES = {
    "Солнечный берег": [
        "Сансет Резорт",
        "Голден Сэндс",
        "Сиа Бриз",
        "Роял Бич",
        "Атлантис",
        "Панорама Бич",
        "Оазис",
        "Империал",
    ],
    "Несебр": [
        "Олд Несебр",
        "Месембрия",
        "Форт Нокс",
        "Аполон",
        "Афродита",
    ],
    "Бургас": [
        "Сий Гарден",
        "Марина Сити",
        "Центральный",
        "Лазур",
    ],
    "Поморие": [
        "Сън Сити",
        "Сансет Кози",
        "Бей Вью",
        "Поморие Бич",
    ],
    "Святой Влас": [
        "Галеон",
        "Марина Диневи",
        "Елените",
        "Вилла Рома",
    ],
    "Равда": [
        "Равда Бич",
        "Сий Вью",
        "Аполон Равда",
    ],
}

FEATURES = [
    "бассейн",
    "паркинг",
    "вид на море",
    "кондиционер",
    "мебель",
    "балкон",
    "лифт",
    "охрана 24/7",
    "ресторан",
    "спа",
    "детская площадка",
    "фитнес",
    "Wi-Fi",
    "сауна",
]


@dataclass
class Property:
    """Test property data."""

    id: str
    title: str
    description: str
    city: str
    district: str
    rooms: int
    price: int
    area: int
    floor: int
    total_floors: int
    distance_to_sea: int
    year_built: int
    features: list[str] = field(default_factory=list)


def generate_description(prop: Property) -> str:
    """Generate realistic description."""
    room_text = "Студия" if prop.rooms == 0 else f"{prop.rooms}-комнатная квартира"
    features_text = ", ".join(prop.features[:4]) if prop.features else "базовая комплектация"

    templates = [
        f'{room_text} в комплексе "{prop.district}", {prop.city}. '
        f"Площадь {prop.area} м², {prop.floor} этаж из {prop.total_floors}. "
        f"{features_text.capitalize()}. До пляжа {prop.distance_to_sea}м. "
        f"Год постройки: {prop.year_built}. Идеально для отдыха или сдачи в аренду.",
        f'Продается {room_text.lower()} в {prop.city}, комплекс "{prop.district}". '
        f"Общая площадь {prop.area} кв.м., этаж {prop.floor}/{prop.total_floors}. "
        f"Расстояние до моря: {prop.distance_to_sea} метров. "
        f"В квартире: {features_text}. Цена: {prop.price:,} EUR.",
        f'Отличное предложение в {prop.city}! {room_text} в популярном комплексе "{prop.district}". '
        f"Площадь: {prop.area} м², этажность: {prop.floor} из {prop.total_floors}. "
        f"Особенности: {features_text}. Море в {prop.distance_to_sea}м. "
        f"Построено в {prop.year_built} году.",
    ]

    return random.choice(templates)


def generate_property(city: str, rooms: int) -> Property:
    """Generate single property."""
    complexes = COMPLEXES.get(city, ["Центральный"])
    district = random.choice(complexes)

    # Price correlates with rooms, city, distance to sea
    base_price = 35000 + rooms * 20000
    city_multiplier = {
        "Солнечный берег": 1.2,
        "Несебр": 1.3,
        "Святой Влас": 1.4,
        "Бургас": 0.9,
        "Поморие": 1.0,
        "Равда": 0.95,
    }.get(city, 1.0)
    price = int(base_price * city_multiplier * random.uniform(0.8, 1.5))

    # Area correlates with rooms
    area = 25 + rooms * 20 + random.randint(-5, 15)

    # Distance to sea (lognormal - more close ones)
    distance_to_sea = int(50 + random.lognormvariate(5, 1))
    distance_to_sea = min(distance_to_sea, 2000)

    # Floors
    total_floors = random.randint(4, 12)
    floor = random.randint(1, total_floors)

    # Features (2-6 random)
    features = random.sample(FEATURES, random.randint(2, 6))

    prop = Property(
        id=str(uuid.uuid4()),
        title=f"{'Студия' if rooms == 0 else f'{rooms}-комнатная квартира'} в {city}",
        description="",  # Will be generated
        city=city,
        district=district,
        rooms=rooms,
        price=price,
        area=area,
        floor=floor,
        total_floors=total_floors,
        distance_to_sea=distance_to_sea,
        year_built=random.randint(2005, 2024),
        features=features,
    )
    prop.description = generate_description(prop)

    return prop


def generate_all_properties(count: int = 100) -> list[Property]:
    """Generate all properties with specified distribution."""
    properties = []

    # Distribution: cities
    city_distribution = {
        "Солнечный берег": 30,
        "Несебр": 25,
        "Бургас": 15,
        "Поморие": 15,
        "Святой Влас": 10,
        "Равда": 5,
    }

    # Distribution: rooms (0=studio, 1, 2, 3, 4+)
    room_distribution = {0: 20, 1: 25, 2: 30, 3: 20, 4: 5}

    for city, city_count in city_distribution.items():
        for _ in range(city_count):
            # Pick rooms according to distribution
            rooms = random.choices(
                list(room_distribution.keys()),
                weights=list(room_distribution.values()),
            )[0]
            properties.append(generate_property(city, rooms))

    random.shuffle(properties)
    return properties[:count]


def main():
    """Generate and save test properties."""
    random.seed(42)  # Reproducible

    properties = generate_all_properties(100)

    output_path = Path("data/test_properties.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "count": len(properties),
        "properties": [asdict(p) for p in properties],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(properties)} properties to {output_path}")

    # Stats
    cities = {}
    rooms = {}
    prices = []
    for p in properties:
        cities[p.city] = cities.get(p.city, 0) + 1
        rooms[p.rooms] = rooms.get(p.rooms, 0) + 1
        prices.append(p.price)

    print(f"\nBy city: {cities}")
    print(f"By rooms: {rooms}")
    print(f"Price range: {min(prices):,} - {max(prices):,} EUR")
    print(f"Price median: {sorted(prices)[len(prices) // 2]:,} EUR")


if __name__ == "__main__":
    main()
