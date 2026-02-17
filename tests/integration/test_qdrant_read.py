#!/usr/bin/env python3
"""
Тест чтения данных из Qdrant (без индексации).
Проверяет поиск и получение точек из существующей коллекции.
"""

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse


project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import os

import pytest
from dotenv import load_dotenv
from qdrant_client import QdrantClient


# Загрузить .env
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://95.111.252.29:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")


def _run_qdrant_read_checks() -> bool:
    """Выполнить проверки чтения из Qdrant."""

    print("=" * 80)
    print("ТЕСТ ЧТЕНИЯ ИЗ QDRANT")
    print("=" * 80)

    print("\n📋 Конфигурация:")
    print(f"   URL: {QDRANT_URL}")
    print(f"   API Key: {'***' + QDRANT_API_KEY[-10:] if QDRANT_API_KEY else 'Не установлен'}")

    try:
        # Подключение
        print("\n🔌 Подключение к Qdrant...")
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
        print("   ✅ Подключено!")

        # Список коллекций
        collections = client.get_collections()
        print(f"\n📦 Коллекций: {len(collections.collections)}")

        if not collections.collections:
            print("   ℹ️  Нет коллекций для тестирования")
            return True

        # Детали первой коллекции
        collection_name = collections.collections[0].name
        print(f"\n🔍 Тестирование коллекции: '{collection_name}'")

        info = client.get_collection(collection_name)
        print(f"   Статус: {info.status}")
        print(f"   Точек: {info.points_count:,}")
        print(f"   Векторов: {info.indexed_vectors_count:,}")

        # Получить несколько точек
        if info.points_count > 0:
            print("\n📄 Получение примера данных (первые 3 точки)...")

            scroll_result = client.scroll(
                collection_name=collection_name,
                limit=3,
                with_payload=True,
                with_vectors=False,  # Don't load vectors (saves memory)
            )

            points, _next_page = scroll_result

            print(f"   ✅ Получено точек: {len(points)}")

            for i, point in enumerate(points, 1):
                print(f"\n   📌 Точка {i} (ID: {point.id}):")
                payload = point.payload or {}

                # Показать основные поля
                for key in ["document_name", "article_number", "chapter", "text"]:
                    if key in payload:
                        value = payload[key]
                        if key == "text":
                            # Обрезать длинный текст
                            value = value[:100] + "..." if len(value) > 100 else value
                        print(f"      {key}: {value}")

        # Тест фильтрации
        print("\n🔎 Тест фильтрации (поиск по article_number)...")

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        scroll_result = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="article_number", match=MatchValue(value="1"))]
            ),
            limit=2,
            with_payload=True,
            with_vectors=False,
        )

        points, _ = scroll_result
        print(f"   ✅ Найдено точек с article_number='1': {len(points)}")

        if points:
            for point in points:
                text = point.payload.get("text", "N/A")[:80]
                print(f"      • {text}...")

        print(f"\n{'=' * 80}")
        print("✅ ВСЕ ТЕСТЫ ЧТЕНИЯ ПРОЙДЕНЫ!")
        print(f"{'=' * 80}\n")

        return True

    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_qdrant_read():
    """Тест чтения из Qdrant."""
    parsed = urlparse(QDRANT_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    if not _is_port_open(host, port):
        pytest.skip(f"Qdrant not running on {host}:{port}")
    assert _run_qdrant_read_checks()


if __name__ == "__main__":
    success = _run_qdrant_read_checks()
    sys.exit(0 if success else 1)
