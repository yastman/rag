#!/usr/bin/env python3
"""
Скрипт для проверки подключения к Qdrant.
Тестирует подключение и выводит информацию о коллекциях.
"""

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse


# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from unittest.mock import patch

import pytest
from qdrant_client import QdrantClient

from src.config.settings import Settings


def _run_qdrant_connection_checks() -> bool:
    """Выполнить проверки подключения к Qdrant."""

    print("=" * 70)
    print("ТЕСТ ПОДКЛЮЧЕНИЯ К QDRANT")
    print("=" * 70)

    # Загрузка настроек
    settings = Settings()

    print("\n📋 Конфигурация:")
    print(f"   QDRANT_URL: {settings.qdrant_url}")
    print(
        f"   API Key: {'***' + settings.qdrant_api_key[-10:] if settings.qdrant_api_key else 'Не установлен'}"
    )

    try:
        # Подключение к Qdrant
        print("\n🔌 Подключение к Qdrant...")
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )

        # Получение списка коллекций
        print("✓ Подключение успешно!")

        collections = client.get_collections()
        print(f"\n📦 Найдено коллекций: {len(collections.collections)}")

        if collections.collections:
            print("\n📊 Список коллекций:")
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
            print("   (Коллекции пока не созданы)")

        print("\n✅ Тест подключения завершен успешно!")
        return True

    except Exception as e:
        print("\n❌ Ошибка подключения к Qdrant:")
        print(f"   {type(e).__name__}: {e}")
        print("\n💡 Проверьте:")
        print("   1. Запущен ли Qdrant: docker ps | grep qdrant")
        print(f"   2. Правильный ли URL в .env: {settings.qdrant_url}")
        print("   3. Доступен ли порт 6333")
        return False


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_qdrant_connection():
    """Проверка подключения к Qdrant."""
    settings = Settings(api_provider="openai", openai_api_key="test-key")
    parsed = urlparse(settings.qdrant_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    if not _is_port_open(host, port):
        pytest.skip(f"Qdrant not running on {host}:{port}")
    with patch.dict(
        "os.environ",
        {"API_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"},
    ):
        assert _run_qdrant_connection_checks()


if __name__ == "__main__":
    success = _run_qdrant_connection_checks()
    sys.exit(0 if success else 1)
