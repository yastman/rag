# Промт для новой сессии: Решение проблемы медленного ingestion на VPS

## Контекст

Работаем на VPS сервере (`ssh vps`, путь `/opt/rag-fresh/`).

Deployment Phase 1 завершён — 9/9 контейнеров healthy. Остался последний пункт: **ingestion документов в Qdrant**.

## Текущая проблема

BGE-M3 embedding service работает на CPU и обрабатывает один батч (32 текста) за 8-50 секунд. При 14 файлах параллельно — запросы встают в очередь и превышают HTTP timeout (300 сек).

**Логи показывают:**
```
httpx.ReadTimeout: timed out
```

## Почему НЕ платное API

Изучили Jina, Voyage, OpenAI, Cohere — ни один не поддерживает sparse + ColBERT векторы. BGE-M3 уникален: генерирует **dense + sparse + ColBERT за один проход**. Для hybrid search + rerank на русском тексте это критично.

## Задача

Завершить ingestion 14 файлов в коллекцию `gdrive_documents_bge`.

## Решение (нужно применить)

1. Увеличить timeout в `.env` на VPS:
```bash
ssh vps "echo 'BGE_M3_TIMEOUT=600' >> /opt/rag-fresh/.env"
```

2. Перезапустить ingestion:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest restart ingestion"
```

3. Мониторить прогресс:
```bash
ssh vps "docker logs vps-ingestion --tail 30 -f"
```

4. Проверить результат (должно быть > 0 points):
```bash
ssh vps "docker compose -f docker-compose.vps.yml exec -T bge-m3 python -c \"import json, urllib.request; print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])\""
```

## Ожидаемое время

~15-20 минут для 14 файлов (~200 чанков суммарно).

## Файлы для справки

- План: `/opt/rag-fresh/docs/plans/2026-02-05-vps-deployment-plan.md`
- Config: `/opt/rag-fresh/src/ingestion/unified/config.py` (читает `BGE_M3_TIMEOUT` из env)
- Writer: `/opt/rag-fresh/src/ingestion/unified/qdrant_writer.py` (использует timeout)

## После успешной индексации

Отметить в плане:
```
- [x] Ingestion запущен, документы проиндексированы
```

И проверить что бот отвечает на вопросы по документам.
