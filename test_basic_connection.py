#!/usr/bin/env python3
"""
Базовый тест подключения к Qdrant (без зависимостей).
Проверяет доступность и список коллекций.
"""

import json
import urllib.request
import urllib.error

# Настройки из .env
QDRANT_URL = "http://95.111.252.29:6333"
QDRANT_API_KEY = "REDACTED_QDRANT_KEY"


def test_qdrant_connection():
    """Тест подключения к Qdrant."""

    print("=" * 80)
    print("ТЕСТ ПОДКЛЮЧЕНИЯ К QDRANT (базовый)")
    print("=" * 80)

    print(f"\n📋 Конфигурация:")
    print(f"   URL: {QDRANT_URL}")
    print(f"   API Key: ***{QDRANT_API_KEY[-10:]}")

    # Тест 1: Проверка версии Qdrant
    print(f"\n🔌 Тест 1: Проверка доступности Qdrant...")
    try:
        req = urllib.request.Request(QDRANT_URL)
        req.add_header("api-key", QDRANT_API_KEY)

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            print(f"   ✅ Qdrant доступен!")
            print(f"   Версия: {data.get('version', 'N/A')}")
            print(f"   Commit: {data.get('commit', 'N/A')[:8]}")
    except urllib.error.HTTPError as e:
        print(f"   ❌ HTTP ошибка {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

    # Тест 2: Получение списка коллекций
    print(f"\n📦 Тест 2: Получение списка коллекций...")
    try:
        req = urllib.request.Request(f"{QDRANT_URL}/collections")
        req.add_header("api-key", QDRANT_API_KEY)

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            collections = data.get("result", {}).get("collections", [])

            print(f"   ✅ Найдено коллекций: {len(collections)}")

            if collections:
                print(f"\n   📊 Список коллекций:")
                for coll in collections:
                    print(f"      • {coll['name']}")
            else:
                print(f"   ℹ️  Коллекции не найдены")

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

    # Тест 3: Детали первой коллекции
    if collections:
        collection_name = collections[0]['name']
        print(f"\n🔍 Тест 3: Детали коллекции '{collection_name}'...")
        try:
            req = urllib.request.Request(f"{QDRANT_URL}/collections/{collection_name}")
            req.add_header("api-key", QDRANT_API_KEY)

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                result = data.get("result", {})

                print(f"   ✅ Информация о коллекции:")
                print(f"      Статус: {result.get('status', 'N/A')}")
                print(f"      Точек (points): {result.get('points_count', 0):,}")
                print(f"      Векторов: {result.get('indexed_vectors_count', 0):,}")
                print(f"      Сегментов: {result.get('segments_count', 0)}")

                # Информация о векторах
                vectors_config = result.get('config', {}).get('params', {}).get('vectors', {})
                if vectors_config:
                    print(f"\n      Конфигурация векторов:")
                    for name, config in vectors_config.items():
                        size = config.get('size', 'N/A')
                        distance = config.get('distance', 'N/A')
                        print(f"         • {name}: {size}D, {distance}")

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return False

    print(f"\n{'=' * 80}")
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print(f"{'=' * 80}\n")

    return True


if __name__ == "__main__":
    import sys
    success = test_qdrant_connection()
    sys.exit(0 if success else 1)
