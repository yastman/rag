# Аудит: алерты не приходят в Telegram (Loki/Promtail → Alertmanager → Telegram)

Дата: 2026-02-04
Репозиторий: `rag-fresh`
Контекст: dev-стек в Docker Compose (`docker-compose.dev.yml`)

## Audit Execution Log (2026-02-04 09:41 UTC)

| Check | Result | Evidence |
|-------|--------|----------|
| Containers healthy | PASS | `make monitoring-status` → all 3 UP |
| Alertmanager config loaded | PASS | Not null receiver, token substituted |
| Bot token valid | PASS | `getMe` → @home_bg_bot |
| Chat ID valid | PASS | `getChat` → private chat OK |
| Direct Telegram API | PASS | `sendMessage` delivered (id: 166104) |
| `make monitoring-test-alert` | PASS | Alert appears in Alertmanager, delivers to Telegram |
| **Loki rules API** | **FAIL** | `400: unable to read /etc/loki/rules/fake` |

**Conclusion:** Test alerts work (bypass Loki), but real log-based alerts fail because Loki cannot load rules.

## 1) Симптом

Алерты из мониторинга “вообще” не приходят в Telegram.

## 2) Проверка цепочки доставки (факты)

### 2.1 Alertmanager → Telegram: работает

Факты:
- Alertmanager поднят и отвечает `healthy` на `http://localhost:9093/-/healthy`.
- Тестовый алерт, отправленный в Alertmanager API (`make monitoring-test-alert`), приводит к попытке Telegram-нотификации:
  - метрика `alertmanager_notifications_total{integration="telegram"}` увеличивается с `0` до `1`.

Вывод:
- Если алерт **попадает** в Alertmanager, он **может** быть отправлен в Telegram (конфиг receiver и сеть до Telegram API функциональны).

### 2.2 Loki Ruler: правила не читаются (ключевая проблема)

Факт:
- Запрос `http://localhost:3100/loki/api/v1/rules` возвращает `400 Bad Request` с текстом:
  - `unable to read rule dir /etc/loki/rules/fake: open /etc/loki/rules/fake: no such file or directory`

Факт:
- Внутри контейнера `dev-loki` правила реально смонтированы как файлы:
  - `/etc/loki/rules/*.yaml`
  - при этом каталога `/etc/loki/rules/fake/` нет.

Вывод:
- Loki Ruler ищет правила в `/etc/loki/rules/<tenant>/` (в dev-режиме tenant по умолчанию — `fake`), а правила лежат в корне `/etc/loki/rules/`.
- Из-за этого Loki **не загружает правила** и **не генерирует** алерты → в Alertmanager ничего не приходит → в Telegram ничего не отправляется.

### 2.3 “Ничего не приходит” также возникает, если мониторинг не запущен

Факт:
- В `docker-compose.dev.yml` сервисы `loki/promtail/alertmanager` помечены профилем `obs` (и `full`), поэтому при `docker compose up -d` (core) они **не стартуют**.

Вывод:
- Если запускать только core-профиль (например, `make docker-up` / `make docker-core-up`), мониторинг и алертинг физически отсутствуют, и алертов в Telegram не будет.

## 3) Root cause (корневая причина)

**Неверный путь монтирования Loki rules:** правила смонтированы в `/etc/loki/rules`, но Loki Ruler ожидает их в `/etc/loki/rules/fake` (tenant subdir).
Следствие: Loki не загружает правила, не генерирует алерты, Alertmanager ничего не получает.

## 4) ТЗ на исправление (минимальный фикс)

### 4.1 Изменения в Docker Compose

Файл: `docker-compose.dev.yml`

Изменить volume mount правил для Loki так, чтобы файлы попадали в tenant-поддиректорию `fake`:

- Было (сейчас):
  - `./docker/monitoring/rules:/etc/loki/rules:ro`
- Должно стать:
  - `./docker/monitoring/rules:/etc/loki/rules/fake:ro`

Примечание:
- Это сохраняет базовый путь `ruler.storage.local.directory: /etc/loki/rules` в `docker/monitoring/loki.yaml`, но добавляет ожидаемую структуру `/etc/loki/rules/<tenant>/...`.

### 4.2 Runbook/UX (чтобы не ловить “тихий” режим)

Файлы: `Makefile`, `docs/ALERTING.md`

Добавить быструю диагностику, чтобы проблема выявлялась за 30 секунд:

1) В `make monitoring-status` добавить проверку `GET /loki/api/v1/rules`:
   - если ответ не `200`, печатать явное предупреждение “Loki rules not loaded (tenant dir mismatch?)”.
2) В `docs/ALERTING.md` добавить заметку:
   - мониторинг живёт в профиле `obs`; `make docker-up` его не поднимает;
   - если “Test alert sent” но сообщений нет — проверить, что смотрят нужный чат и что это отдельный alerting-бот (не основной бот).

## 5) Критерии приёмки

После внесения правок:

1) `make monitoring-up` поднимает `dev-loki/dev-promtail/dev-alertmanager` в состоянии `healthy`.
2) `curl -sS -i http://localhost:3100/loki/api/v1/rules` возвращает `200` и JSON со списком rule groups (нет ошибки про `/etc/loki/rules/fake`).
3) Loki видит правила из `docker/monitoring/rules/*.yaml` (достаточно пункта 2).
4) `make monitoring-test-alert` увеличивает `alertmanager_notifications_total{integration="telegram"}` минимум на `+1`.
5) На реальном инциденте (например, остановка `dev-bot` на >2 минут) срабатывает соответствующее правило (например `BotContainerDown`) и уходит в Telegram.

## 6) Риски/совместимость

- Изменение касается только dev-монтирования правил в Loki (профиль `obs/full`).
- Не меняет Alertmanager/TG конфиг и не раскрывает токены.

## 7) Валидация (факт)

Проверено 2026-02-04 локально в dev-окружении Docker Compose.

- Containers healthy: `PASS` (`dev-loki`, `dev-promtail`, `dev-alertmanager` в `healthy`)
- Loki rules API: `PASS` (`GET /loki/api/v1/rules` → `HTTP 200`)
- Rules loaded: `PASS` (в `/loki/api/v1/rules` найдено `53` вхождения `- alert:`)
- Promtail → Loki ingestion: `PASS` (LogQL `{container="dev-loki"}` за 10 мин возвращает `>= 1` stream и события)
- Telegram notification sent: `PASS` (`alertmanager_notifications_total{integration="telegram"}` увеличился `1 → 2`, `alertmanager_notification_errors_total{integration="telegram"} = 0`)

## 7) Заметка: Alertmanager не логирует успешные отправки

Alertmanager логирует только ошибки нотификаций (ERROR level). Успешные dispatch'ы не видны в логах - это нормальное поведение.

Для верификации использовать:
1. `make monitoring-test-alert` + проверка Telegram
2. Метрики: `curl localhost:9093/metrics | grep alertmanager_notifications`
