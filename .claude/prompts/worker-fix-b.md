W-FIX-B: Починить 16 тестов в test_preflight.py + test_bot_handlers.py

Работай из /repo

Проблемы:
- Моки не перехватывают реальные Redis/Qdrant соединения
- Тесты попадают в запущенные Docker сервисы вместо моков
- Patch targets неправильные (патчится где определено, а не где используется)

Шаги:

1. Прочитай tests/unit/test_preflight.py — найди все patch декораторы
2. Прочитай telegram_bot/preflight.py — пойми откуда импортируются Redis/httpx
3. Исправь patch targets: патчить нужно ТАМ ГДЕ ИСПОЛЬЗУЕТСЯ, не где определено
   Например: patch("telegram_bot.preflight.redis.Redis") а не patch("redis.Redis")
4. Замени MagicMock на AsyncMock для async Redis операций
5. Прочитай tests/unit/test_bot_handlers.py — тесты test_start_* падают на PreflightError
6. Mock check_dependencies в bot_handlers тестах чтобы не вызывать реальные сервисы
7. Запусти: uv run pytest tests/unit/test_preflight.py tests/unit/test_bot_handlers.py -v --tb=short
8. Фикси пока все зелёные

После успеха:
- git add tests/unit/test_preflight.py tests/unit/test_bot_handlers.py
- git commit -m "fix(tests): repair preflight and bot handler tests — correct mock targets

16 tests fixed: patch where-used not where-defined, AsyncMock for
async Redis ops, mock check_dependencies in bot init.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /repo/logs/worker-fix-b.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-FIX-B COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
