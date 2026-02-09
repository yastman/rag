W-CACHE: Unit тест для /cache_stats handler бота

GitHub Issue: #52 — P1: bot /cache_stats handler test
Работай из /home/user/projects/rag-fresh

Шаги:

1. Прочитай telegram_bot/bot.py — найди handler для /cache_stats команды
2. Прочитай tests/unit/test_bot_handlers.py — паттерн тестов handlers (test_cmd_start, test_cmd_stats)
3. Добавь тест в tests/unit/test_bot_handlers.py (или создай отдельный файл если лучше):

   Тест test_cmd_cache_stats:
   - Mock message с command /cache_stats
   - Mock cache service (return stats dict)
   - Проверь что bot отвечает с cache statistics
   - Проверь формат ответа

4. Запусти: uv run pytest tests/unit/test_bot_handlers.py -v -k cache_stats
5. Фикси пока зелёный

После успеха:
- git add тестовый файл
- git commit -m "test(bot): add unit test for /cache_stats handler

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /home/user/projects/rag-fresh/logs/worker-cache-stats.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения:
TMUX="" tmux send-keys -t "claude:1" "W-CACHE COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
