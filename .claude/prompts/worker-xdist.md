W-XDIST: Сравни sequential vs parallel unit тесты

Работай из /repo
GitHub Issue: #44 — Task 7

Шаги:

1. Запусти sequential baseline и запиши время:
   time uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -5 | tee /repo/logs/xdist-sequential.txt

2. Запусти parallel с xdist:
   time uv run pytest tests/unit/ -q --tb=no -n auto 2>&1 | tail -5 | tee /repo/logs/xdist-parallel.txt

3. Сравни результаты и запиши в /repo/logs/xdist-comparison.txt:
   - Sequential: время, passed/failed
   - Parallel (-n auto): время, passed/failed
   - Speedup: X раз быстрее
   - Новые фейлы от параллелизации (если есть)

4. Если parallel вызывает НОВЫЕ фейлы (race conditions) — запиши какие и почему

НЕ делай git commit.

Логирование в /repo/logs/worker-xdist.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-XDIST COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
