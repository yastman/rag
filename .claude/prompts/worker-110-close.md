W-110: Close issue #110 — fix bugs + add queries + baseline run

Работай из /repo. Без остановок.

SKILLS:
1. /verification-before-completion — после фиксов и перед финальным прогоном

ЗАДАЧИ:

ЗАДАЧА 1: Fix Makefile — telegram-bot -> bot
В Makefile строка ~766 (validate-traces target) используется несуществующий сервис telegram-bot.
В docker-compose.dev.yml сервис называется bot.
Замени telegram-bot на bot в обоих targets (validate-traces и validate-traces-fast).
Проверь: grep telegram-bot Makefile — должно быть 0 совпадений в validate targets.

ЗАДАЧА 2: Add GDRIVE_BGE_QUERIES to scripts/validate_queries.py
gdrive_documents_bge — те же Bulgarian property docs что contextual_bulgaria_voyage, но с BGE-M3 embeddings.
Нужно добавить минимум 20-30 запросов на русском по болгарской недвижимости.

Добавь массив GDRIVE_BGE_QUERIES: list[ValidationQuery] с collection="gdrive_documents_bge":
- 10 easy: простые вопросы про цену, район, тип недвижимости
  Примеры: "квартира в Несебре", "студия на Солнечном берегу", "цена дома в Равде", "аренда апартаментов", "однокомнатная квартира цена", "недвижимость в Болгарии", "жильё у моря", "купить квартиру Бургас", "сколько стоит студия", "квартира первая линия"
- 10 medium: с фильтрами и условиями
  Примеры: "квартира до 50000 евро с мебелью", "двухкомнатная с видом на море", "новостройка с рассрочкой", "комплекс с бассейном и паркингом", "квартира с ремонтом под ключ", "апартаменты рядом с пляжем до 40000", "студия в закрытом комплексе", "жильё для сдачи в аренду инвестиции", "квартира с балконом и кондиционером", "дом с участком в пригороде"
- 10 hard: сравнения, аналитика, сложные запросы
  Примеры: "сравни цены Солнечный берег vs Святой Влас 2024", "что лучше купить студию или однокомнатную для инвестиций", "комплексы с управляющей компанией и гарантированной арендой", "найди все варианты с рассрочкой на 2-3 года без первого взноса", "какой район в Бургасской области самый перспективный для покупки", "апартаменты с двумя спальнями в Harmony Suites или Tarsis Club", "покупка через юрлицо vs физлицо налоги", "квартира с документами для ВНЖ в Болгарии", "самые дешёвые варианты на первой линии с мебелью", "что включает цена под ключ: мебель, техника, ремонт"

ЗАДАЧА 3: Update get_queries_for_collection mapping
В scripts/validate_queries.py функция get_queries_for_collection() — добавь маппинг:
  elif collection == "gdrive_documents_bge":
      result.extend(GDRIVE_BGE_QUERIES)

ЗАДАЧА 4: Update COLLECTIONS_TO_CHECK in validate_traces.py
Убедись что gdrive_documents_bge в списке коллекций и detect_runner_mode возвращает "langgraph_bge" для него.

ЗАДАЧА 5: Update unit tests
- test_validate_queries.py — добавь тест для GDRIVE_BGE_QUERIES count (30) и get_queries_for_collection("gdrive_documents_bge")
- Запусти: uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v

ЗАДАЧА 6: Lint + format
uv run ruff check scripts/validate_traces.py scripts/validate_queries.py
uv run ruff format scripts/validate_traces.py scripts/validate_queries.py

ЗАДАЧА 7: Commit
git add scripts/validate_queries.py scripts/validate_traces.py tests/unit/test_validate_queries.py Makefile
git commit (conventional: fix(validation): add gdrive_bge queries + fix Makefile service name (#110))

ЗАДАЧА 8: Run baseline
uv run python scripts/validate_traces.py --collection gdrive_documents_bge --report
Ожидаемый результат: cold n>=30, cache-hit n>=10.
Если скрипт упал — прочитай ошибку, пофикси, перезапусти. Не останавливайся.

ЗАДАЧА 9: Show report
cat docs/reports/2026-02-10-validation-*.md (последний файл)
ls -la docs/reports/

MCP TOOLS:
- Context7: если нужна документация Langfuse SDK
- Exa: для поиска примеров

ТЕСТЫ:
- scripts/validate_queries.py -> tests/unit/test_validate_queries.py
- scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
3. НЕ останавливайся — фикс, тесты, прогон, отчёт — всё подряд.

ЛОГИРОВАНИЕ в /repo/logs/worker-110-close.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-110-close.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-110-close.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-110-close.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-110 COMPLETE — проверь logs/worker-110-close.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
