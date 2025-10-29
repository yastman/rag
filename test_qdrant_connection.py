#!/usr/bin/env python3
"""
Скрипт для проверки подключения к Qdrant.
Тестирует подключение и выводит информацию о коллекциях.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from qdrant_client import QdrantClient
from src.config.settings import Settings


def test_qdrant_connection():
    """Проверка подключения к Qdrant."""

    print("=" * 70)
    print("ТЕСТ ПОДКЛЮЧЕНИЯ К QDRANT")
    print("=" * 70)

    # Загрузка настроек
    settings = Settings()

    print(f"\n📋 Конфигурация:")
    print(f"   QDRANT_URL: {settings.qdrant_url}")
    print(f"   API Key: {'***' + settings.qdrant_api_key[-10:] if settings.qdrant_api_key else 'Не установлен'}")

    try:
        # Подключение к Qdrant
        print(f"\n🔌 Подключение к Qdrant...")
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None
        )

        # Получение списка коллекций
        print(f"✓ Подключение успешно!")

        collections = client.get_collections()
        print(f"\n📦 Найдено коллекций: {len(collections.collections)}")

        if collections.collections:
            print(f"\n📊 Список коллекций:")
            for collection in collections.collections:
                try:
                    info = client.get_collection(collection.name)
                    print(f"\n   • {collection.name}")
                    print(f"     - Точек (vectors): {info.points_count}")
                    print(f"     - Размерность: {info.config.params.vectors.size}")
                    print(f"     - Метрика: {info.config.params.vectors.distance}")
                except Exception as e:
                    print(f"   • {collection.name} - ошибка получения деталей: {e}")
        else:
            print(f"   (Коллекции пока не созданы)")

        print(f"\n✅ Тест подключения завершен успешно!")
        return True

    except Exception as e:
        print(f"\n❌ Ошибка подключения к Qdrant:")
        print(f"   {type(e).__name__}: {e}")
        print(f"\n💡 Проверьте:")
        print(f"   1. Запущен ли Qdrant: docker ps | grep qdrant")
        print(f"   2. Правильный ли URL в .env: {settings.qdrant_url}")
        print(f"   3. Доступен ли порт 6333")
        return False


if __name__ == "__main__":
    success = test_qdrant_connection()
    sys.exit(0 if success else 1)
