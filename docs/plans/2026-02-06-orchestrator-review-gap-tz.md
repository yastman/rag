# ТЗ: Оркестраторский Gap-Review (актуализировано)

Дата: 2026-02-06
Режим: ревью + ТЗ (без фиксов/тестов в этом цикле)

## 1) Что закрыто и удалено из активного плана (проверено)
- Закрыто: переход query/ingestion sparse на BGE-M3 (с сохранением имени sparse-поля `bm42` для обратной совместимости).
  Проверено: `telegram_bot/bot.py:622`, `src/ingestion/unified/qdrant_writer.py:95`
- Закрыто: убраны bind-mount исходников из `vps-ingestion` в VPS compose.
  Проверено: `docker-compose.vps.yml:281`
- Закрыто: ColBERT timeout вынесен из hardcode в env (`COLBERT_TIMEOUT`, default 120s).
  Проверено: `telegram_bot/services/colbert_reranker.py:37`
- Закрыто: graceful degradation при падении rerank (ответ не срывается).
  Проверено: `telegram_bot/bot.py:474`
- Закрыто: ограничение rerank candidates добавлено.
  Проверено: `telegram_bot/config.py:54`, `telegram_bot/bot.py:429`

## 2) Активные задачи (оставшиеся + новые)

| ID | Приоритет | Статус | Что осталось / проблема | Доказательство |
|---|---|---|---|---|
| GAP-03 | P0 | `partial` | `preflight/bootstrap` добавлены, но не доведены до рабочего состояния | `src/ingestion/unified/cli.py:68`, `src/ingestion/unified/cli.py:155` |
| GAP-19 | P0 | `open` | `bootstrap` ломается в контейнере ingestion: `ModuleNotFoundError: scripts` | `src/ingestion/unified/cli.py:157`; runtime check inside container |
| GAP-04 | P1 | `partial` | Manifest-identity реализован, но по content-hash (не Drive ID), возможны коллизии по одинаковому контенту | `src/ingestion/unified/flow.py:67`, `src/ingestion/unified/manifest.py:67` |
| GAP-20 | P1 | `open` | `preflight` дает ложный fail на dense из-за жёсткого timeout 10s для CPU | `src/ingestion/unified/cli.py:75`, `src/ingestion/unified/cli.py:97` |
| GAP-05 | P1 | `partial` | Docling profiles внедрены, но профиль `speed` фактически не включает `table_mode=fast` по умолчанию (логическая нестыковка условий) | `src/ingestion/docling_client.py:28`, `src/ingestion/docling_client.py:136` |
| GAP-06 | P1 | `partial` | В compose указан stable LiteLLM, но runtime еще на RC-образе (дрейф деплоя) | `docker-compose.vps.yml:184`; runtime `docker compose ps` показывает `v1.81.3.rc.3` |
| GAP-07 | P1 | `open` | Alias `gpt-4o-mini` по-прежнему мапится на `zai-glm-4.7` (операционная неоднозначность) | `docker/litellm/config.yaml:8` |
| GAP-08 | P1 | `open` | Healthcheck бота только process-level (через Dockerfile), без dependency-preflight (`qdrant/litellm/redis`) | `telegram_bot/Dockerfile:49`; в `docker-compose.vps.yml` нет bot healthcheck блока |
| GAP-09 | P1 | `partial` | Qdrant bootstrap/policy не согласованы с unified-пайплайном (индексы/схема для gdrive не гарантированы единым путём) | `src/ingestion/unified/cli.py:157`, `scripts/setup_qdrant_collection.py:129` |
| GAP-10 | P1 | `open` | Secret management: ключи в plain env | `docker-compose.vps.yml:190`, `docker-compose.vps.yml:222` |
| GAP-11 | P2 | `partial` | В проекте остаются legacy + unified ingestion пути | `src/ingestion/gdrive_flow.py:1`, `src/ingestion/unified/flow.py:1` |
| GAP-12 | P2 | `partial` | Документация частично отстает от runtime | `CLAUDE.md:26` |
| GAP-13 | P2 | `open` | Infra checklist phase2 не закрыт | `docs/plans/2026-02-05-vps-phase2-plan.md:685` |
| GAP-14 | P2 | `open` | ColBERT multivector в Qdrant (схема+ingestion+reindex) не внедрен | `src/ingestion/unified/qdrant_writer.py:423` |
| GAP-18 | P2 | `partial` | timeout-профиль bge-m3 клиентов частично выровнен, но env-политика в compose для bot не зафиксирована явно | `telegram_bot/services/bge_m3_dense.py:38`, `docker-compose.vps.yml:220` |
| GAP-22 | P1 | `open` | Dead wiring BM42: сервис/depends_on/env остались, хотя код уже не использует BM42 | `docker-compose.vps.yml:161`, `docker-compose.vps.yml:234`, `docker-compose.vps.yml:244`, `telegram_bot/config.py:62` |

## 3) Новый ревью-вывод по багам
- Баг подтвержден: `bootstrap` в контейнерном runtime неработоспособен (`scripts` не в image path).
- Баг подтвержден: `preflight` может фейлиться на dense при CPU latency хвосте.
- Баг подтвержден: runtime-deploy drift по LiteLLM (compose != запущенный контейнер).
- Риск подтвержден: manifest на content-hash может склеить разные файлы с одинаковым содержимым.

## 4) Приоритетный порядок фиксов (следующий цикл)
1. `P0` Починить `bootstrap` для контейнерного запуска (`GAP-19`).
2. `P0/P1` Сделать preflight timeout-политику адаптивной к CPU (`GAP-20`).
3. `P1` Убрать dead BM42 wiring в compose/bot config (`GAP-22`).
4. `P1` Довести LiteLLM до фактического stable runtime (без дрейфа) (`GAP-06`).
5. `P1` Закрыть Docling profile-логическую нестыковку `speed` (`GAP-05`).
6. `P1` Перевести identity на Drive-ID strategy или гибрид (Drive ID first, content-hash fallback) (`GAP-04`).

## 5) Текущее состояние
- Нельзя утверждать "все выполнено и багов нет".
- По моему повторному ревью есть закрытые пункты, но остаются блокирующие и новые дефекты (см. `GAP-19`, `GAP-20`).
