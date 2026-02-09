W-FIX-D: Починить 12 тестов в test_vectorizers.py

Работай из /repo

Проблемы:
- Mock side_effect list имеет только 1 entry но конструктор вызывается несколько раз -> StopIteration
- Patched BaseVectorizer mock не возвращает правильные instances

Шаги:

1. Прочитай tests/unit/test_vectorizers.py — найди все side_effect=
2. Прочитай telegram_bot/services/vectorizers.py (или где определён класс) — пойми сколько раз вызывается конструктор
3. Замени side_effect на return_value где нужен один объект
4. Или добавь достаточно entries в side_effect list
5. Убедись что mock возвращает объекты с нужными атрибутами (url, timeout, dims=768)
6. Запусти: uv run pytest tests/unit/test_vectorizers.py -v --tb=short
7. Фикси пока все зелёные

После успеха:
- git add tests/unit/test_vectorizers.py
- git commit -m "fix(tests): repair vectorizer tests — fix mock side_effect exhaustion

12 tests fixed: use return_value instead of side_effect for singleton mocks,
ensure proper attribute setup on mock instances.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /repo/logs/worker-fix-d.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-FIX-D COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
