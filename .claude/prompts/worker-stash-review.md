W-STASH: Проверь и примени stashed фиксы тестов

Работай из /home/user/projects/rag-fresh

Контекст: предыдущий воркер W-TEST работал над фиксом unit тестов (Task 6) 50 минут.
Его изменения сохранены в git stash. Нужно проверить что там и применить если полезно.

Шаги:

1. Посмотри что в stash: git stash show -p
2. Проанализируй изменения — что было пофикшено, что нет
3. Если изменения полезные (фиксы тестов, skipы для docker-dependent тестов):
   - git stash pop
   - Проверь что изменения корректные
   - Запусти затронутые тесты: uv run pytest {changed_test_files} -v --tb=short
   - Если зелёные — коммить
   - git add конкретные файлы
   - git commit -m "fix(tests): apply test fixes from baseline analysis

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
4. Если изменения мусорные — git stash drop и запиши в лог почему

Запиши в лог что было в stash и что сделал.

Логирование в /home/user/projects/rag-fresh/logs/worker-stash-review.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения:
TMUX="" tmux send-keys -t "claude:1" "W-STASH COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
