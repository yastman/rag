# План аудита: алерты не приходят в Telegram (Loki → Alertmanager → Telegram)

## Цель

Найти точную причину, почему алерты из “центра мониторинга” не доставляются в Telegram **вообще**, и сформировать список конкретных действий/правок для восстановления доставки.

## Область

Только аудит/диагностика (без внесения изменений в код/конфиги в рамках этого плана).

## Карта потока (что должно работать)

1) Docker логи сервисов → 2) `promtail` пушит в `loki` → 3) `loki ruler` оценивает правила (`docker/monitoring/rules/*.yaml`) → 4) `loki` отправляет алерты в `alertmanager` → 5) `alertmanager` роутит в `telegram_configs` → 6) Telegram Bot API доставляет в нужный `chat_id`.

## Гипотезы (от самых частых)

1) Monitoring-профиль не поднят (`obs/full`), контейнеров нет или не healthy.
2) `Alertmanager` стартует в режиме `null receiver` из-за пустого `TELEGRAM_ALERTING_BOT_TOKEN`.
3) `TELEGRAM_ALERTING_CHAT_ID` неверный (личка vs группа `-100…`), либо бот не имеет права писать (нет `/start`, бот не в группе, нет прав).
4) Роутинг/лейблы не матчятся (алерты уходят не в тот receiver / подавляются inhibit-правилом).
5) Доставка в Telegram ломается на API (403/400/429), но это не видно из-за отсутствия/непросматриваемости логов.
6) Проблема в Loki Ruler (правила не подхватились/не evalятся/не шлются в Alertmanager).

## Что собрать (артефакты аудита)

Важно: **не публиковать токены**. Любые выводы с токенами — редактировать/маскировать.

### A) Статус контейнеров

- Вывод `docker ps` для `dev-loki`, `dev-promtail`, `dev-alertmanager`.
- Вывод `make monitoring-status`.

### B) Конфиг Alertmanager “как он реально запущен”

- Содержимое `/etc/alertmanager/alertmanager.yml` **изнутри контейнера** с замаскированным `bot_token` и `chat_id`.
- Логи `dev-alertmanager` за последние 10–30 минут с фильтром по `telegram|notify|error|warn`.

### C) Жизнь алертов внутри Alertmanager

- Запрос в Alertmanager API:
  - `/api/v2/status` (общий статус)
  - `/api/v2/alerts` (видит ли он firing/resolved алерты)
  - `/api/v2/receivers` (какие receivers активны)
- Запуск “ручного” тестового алерта:
  - `make monitoring-test-alert`
  - После этого повторно `/api/v2/alerts` и логи Alertmanager.

### D) Loki Ruler → Alertmanager связь

- Логи `dev-loki` (по словам `ruler`, `alertmanager`, `notification`, `error`).
- Проверка, что правила реально подмонтированы: каталог `/etc/loki/rules` внутри контейнера.
- Если есть firing в Loki, но нет в Alertmanager — фокус на `alertmanager_url` в `docker/monitoring/loki.yaml`.

### E) Telegram Bot API (проверка прав и chat_id)

- Проверка `getMe` для токена (валидность бота).
- Проверка `getChat` для `chat_id` (существует ли чат и видит ли его бот).
- Попытка “ручного” `sendMessage` в тот же `chat_id` (минимальное сообщение, HTML можно отключить).

## Диагностическая последовательность (пошагово)

1) Убедиться, что мониторинг поднят именно с профилем `obs/full` и контейнеры healthy.
2) Проверить, что Alertmanager НЕ в null-конфиге и в `alertmanager.yml` реально стоит Telegram receiver.
3) Отправить тестовый алерт (через `monitoring-test-alert`) и:
   - увидеть его в `/api/v2/alerts`,
   - проверить лог Alertmanager на попытку нотификации в Telegram.
4) Если Alertmanager алерт видит, но Telegram пуст:
   - проверить Telegram API вручную (`getMe`, `getChat`, `sendMessage`),
   - подтвердить права/`/start`/группу и корректный `chat_id`.
5) Если Alertmanager алертов не видит:
   - разделить проблему на “Loki не генерит” vs “Loki не шлёт в Alertmanager”,
   - проверять Loki Ruler и правила.

## Решение аудита (как оформлять вывод)

### 1) Диагноз (одна строка)

Например: “Alertmanager работает, алерт видит, но Telegram API отвечает 403 (бот не имеет права писать в чат)”.

### 2) Доказательства (коротко)

Список 3–6 пунктов “факт → источник” (команда/эндпоинт/лог).

### 3) План фикса

Чёткий список действий (конфиг/env/документация), без “возможно”.

### 4) Критерии приёмки

- `make monitoring-up` поднимает `dev-loki/dev-promtail/dev-alertmanager` в `healthy`.
- `make monitoring-test-alert` приводит к сообщению в Telegram ≤ 60 секунд.
- В логах Alertmanager нет ошибок Telegram на тестовом алерте.

## Релевантные файлы

- `docker-compose.dev.yml` (профили, entrypoint Alertmanager, env)
- `docker/monitoring/alertmanager.yaml` (route/receivers/telegram_configs)
- `docker/monitoring/loki.yaml` (ruler, `alertmanager_url`)
- `docker/monitoring/promtail.yaml` (scrape)
- `docker/monitoring/rules/*.yaml` (правила)
- `Makefile` (`monitoring-*` таргеты)
