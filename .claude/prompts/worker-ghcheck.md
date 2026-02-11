W-GHCHECK: Проверить GitHub замечания по #101/#122/#123/#124 и добавить comment

Работай из /home/user/projects/rag-fresh

КОНТЕКСТ: Коммит f225773 содержит fix(review) для issues #101, #122, #123, #124.
Изменённые файлы: validate_traces.py, bot.py, cache.py, retrieve.py, rewrite.py, state.py, smoke tests, unit tests.

ЗАДАЧИ:

1. Прочитать комментарии к каждому issue:
   gh issue view 101 --comments
   gh issue view 122 --comments
   gh issue view 123 --comments
   gh issue view 124 --comments

2. Проверить что коммит f225773 адресует замечания. Посмотреть diff:
   git show f225773 --stat
   git show f225773

3. Для каждого issue где замечания учтены — добавить комментарий:
   gh issue comment 101 --body "Follow-up fixes applied in f225773. Changes: validate_traces.py aggregation fix."
   gh issue comment 122 --body "Follow-up fixes applied in f225773. Changes: bot.py qdrant_timeout usage."
   gh issue comment 123 --body "Follow-up fixes applied in f225773. Changes: cache.py/retrieve.py/rewrite.py traced_pipeline integration."
   gh issue comment 124 --body "Follow-up fixes applied in f225773. Changes: state.py provider_metadata fields, smoke test updates."

   НО: адаптируй текст комментария к реальному содержимому diff. Не копируй слепо — прочитай diff и напиши точно что было исправлено.

4. Если есть незакрытые замечания — записать в лог что именно не учтено.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-ghcheck.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-ghcheck.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-ghcheck.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-ghcheck.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:node" "W-GHCHECK COMPLETE — проверь logs/worker-ghcheck.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:node" Enter
