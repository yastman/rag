# Красные флаги и чеклист

Самопроверка оркестратора. Перечитай при сомнениях.

## СТОП — красные флаги

**Контекст-бюджет:**
- `Read` файла > 50 строк → worker
- Исследование > 500 токенов → worker/субагент
- На 3-й issue контекст > 80K → утечка

**Классификация:**
- CLEAR → Opus worker (Sonnet справится, дешевле 5x)
- TRIVIAL/CLEAR inline (всегда worker, даже 1 строка)
- COMPLEX → Sonnet без плана (провал)
- Все issues одного уровня (классифицируй каждый)
- Haiku оценивает сложность (только DO/SKIP/STALE/UNCERTAIN, сложность — orch)
- >5 воркеров одновременно (координация > польза)
- Контракт D никогда не используется (проверь: есть ли путь в classification flowchart)

**Стратегия:**
- Orch пишет код inline (**ВСЕГДА** worker)
- Нет `--model sonnet` (дефолт = Opus = $$$)
- Последовательно для РАЗНЫХ файлов (параллельно)
- Orch мержит/PR (workers сами)
- Grep/Glob для понимания зависимостей вместо `grepai_trace_callers` (semantic + call graph точнее)
- Классификация без GrepAI (Фаза 2.3) — orch не понимает scope, неверная сложность

**MCP tools:**
- Read для файлов >50 строк при анализе (используй context-mode execute_file)
- Bash для output >20 строк (используй context-mode execute или batch_execute)
- Только GrepAI без LSP для type-checking (LSP hover/findReferences даёт точные типы)
- Code review через Read diff (используй context-mode execute — diff в sandbox, не в контекст)
- Нет LSP findReferences при file reservation (неточные резервации → merge conflicts)
- Нет batch_execute для сбора project_scope (N Bash вызовов засоряют контекст)

**SDK-first:**
- Worker пишет кастомный код для задачи, покрытой SDK из реестра
- Orch пропустил Phase 2.7 при наличии `.claude/rules/sdk-registry.md`
- Worker не проверил `{sdk_registry_excerpt}` перед кодом
- Контракт C план без секции "SDK Coverage"
- Worker добавил новый SDK/паттерн, но orch не обновил реестр (Фаза 5.2)
- Новая зависимость в pyproject.toml без записи в реестре

**Скиллы:**
- Worker коммит БЕЗ `Skill(skill="requesting-code-review")`
- Worker коммит БЕЗ `Skill(skill="verification-before-completion")`
- Worker код БЕЗ `Skill(skill="test-driven-development")`
- Worker retry БЕЗ `Skill(skill="systematic-debugging")`
- Контракт B/D без `Skill(skill="executing-plans")`
- Контракт C/D без `Skill(skill="writing-plans")`
- Worker делает SDK исследование сам → orch субагент ДО запуска

**Сигнализация:**
- Нет `mkdir -p .signals` при инициализации
- Worker пишет сигнал в tmux вместо `.signals/worker-{name}.json`
- Orch не переименовывает обработанные сигналы (`done-*`)
- Нет watchdog таймаута при запуске worker
- Сигнал без атомарной записи (echo > file, без .tmp → mv)
- inotifywait отслеживает `create` вместо `moved_to` (при атомарной записи)
- Part-worker создаёт PR (только финальный worker создаёт PR)

**Безопасность:**
- Промт inline в send-keys (файл!)
- `claude --worktree` для tmux workers (`git worktree add` ТОЛЬКО)
- `tmux new-session` / нет `TMUX=""`
- Нет `--dangerously-skip-permissions`
- `.env` скопирован в worktree (только `.env.test`!)
- Нет `{reserved_files}` при параллельных workers

**Верификация:**
- Только маркеры `[SKILL:*]` без артефактной проверки
- Маркеры есть, но `make check` не пройден → FAIL
- Нет тестов в worktree → FAIL (даже если маркер `[SKILL:tdd]`)

## Рационализации

| Отговорка | Реальность |
|-----------|------------|
| "Быстрее написать кастом" | SDK уже протестирован и поддерживается. Кастом = tech debt. |
| "SDK слишком сложный" | Прочитай как_у_нас в реестре — паттерн уже отработан. |
| "Мне нужна кастомная логика" | 90% случаев SDK покрывает. Проверь gotchas в реестре. |
| "Не нашёл в SDK" | Context7 query-docs? Exa search? Реестр проверил? |
| "Реестр обновлю потом" | Потом = никогда. Фаза 5.2 = сразу после PASS. |
| "Сам быстрее inline" | Opus inline = $15. Sonnet worker = $3. |
| "Sonnet справится без плана" | COMPLEX без плана = провал. |
| "Детальный план — сам выполню" | План = идеальный промт для Sonnet. |
| "Один worker на всё" | VERY COMPLEX → N параллельных Sonnet. |
| "Пока жду — посмотрю код" | 0 токенов пока ждёшь. Жди. |
| "Скиллы замедлят worker" | Скиллы = quality gate. Без них → перезапуск = дороже. |
| "TDD overkill для 3 строк" | TDD = 30 сек. Без него — баг в PR. |
| "Review — лишний шаг" | Review ловит 20% ошибок. |
| "Маркеры — бюрократия" | 1 echo = 0 токенов. Без него orch не верифицирует. |
| "Worker сам найдёт SDK документацию" | Sonnet субагент = $0.50. Worker ресёрчит = $3+. |
| "Grep хватит для понимания кода" | Grep = literal text. GrepAI = semantic + call graph. Используй оба. |
| "Haiku определит сложность" | Haiku фильтрует DO/SKIP/STALE/UNCERTAIN. Сложность — orch. |
| "Haiku правильно определил вне скоупа" | Haiku не знает скоуп. SKIP только с доказательством (PR#, дубль#). Иначе → DO. |
| "send-keys надёжнее файлов" | send-keys = UDP без ACK. Файл = гарантия доставки. |
| "Таймаут не нужен, worker доделает" | Зависший worker = неверная классификация. Таймаут → эскалация. |
| "Файловые резервации — оверкилл" | 2 worker'а в одном файле = merge conflict = оба потеряны. |
| "Этот issue надо распараллелить" | Opus решает, не orch. Если Opus сказал sequential — sequential. |
| "Opus ошибся, задачи явно независимы" | Opus видел код и зависимости. Orch видел только тело issue. Доверяй Opus. |
| "Read diff быстрее context-mode" | Read загружает diff в контекст (~5K токенов). context-mode execute — 0 токенов, summary от intent. |
| "LSP overkill, GrepAI хватит" | GrepAI = semantic. LSP = точные типы и references. Для file reservation нужны оба. |
| "batch_execute сложнее N Bash" | 1 batch_execute = 1 round-trip. N Bash = N round-trips + N × output в контексте. |

## Чеклист (перед запуском)

- [ ] `mkdir -p .signals` выполнен
- [ ] `orch_log` хелпер определён
- [ ] Фаза 2 (классификация) для каждого issue
- [ ] Haiku только для фильтрации (DO/SKIP/STALE/UNCERTAIN), НЕ для сложности
- [ ] `{project_scope}` собран для Haiku (head README + ls src + git log)
- [ ] Правильная модель: CLEAR/MEDIUM → `--model sonnet`, COMPLEX → Opus
- [ ] Правильный контракт (A/B/C/D)
- [ ] COMPLEX+: Волна 1 (исследование) до Волны 2 (выполнение)
- [ ] Фаза 2.5: file overlap проверен, `{reserved_files}` назначены
- [ ] Фаза 2.3 (GrepAI + LSP + context-mode) — semantic search, trace, types, references
- [ ] Фаза 2.7 (SDK контекст) — ОБЯЗАТЕЛЬНА если `.claude/rules/sdk-registry.md` существует
- [ ] `{sdk_registry_excerpt}` включён в промт каждого worker'а
- [ ] project_scope через batch_execute (НЕ inline Bash)
- [ ] `git worktree add` (НЕ `claude --worktree`)
- [ ] `.env.test` скопирован в worktree (НЕ `.env`)
- [ ] Промт в файл (НЕ inline)
- [ ] `<HARD-GATE>` с требованиями скиллов в промте
- [ ] Сигнализация через `.signals/` (НЕ tmux send-keys)
- [ ] `--dangerously-skip-permissions`
- [ ] Watchdog таймаут запущен для каждого worker (включая B-final)
- [ ] ≤5 параллельных воркеров
- [ ] При parallel: part-workers используют B-part (без PR), только финальный — B с {Общий финал}
- [ ] Сигналы через атомарную запись (.tmp → mv)

## Чеклист (Фаза 5 — при сигнале)

- [ ] Прочитать `.signals/worker-{name}.json`
- [ ] **Уровень 0: Code Review** через context-mode execute (diff в sandbox, НЕ Read)
- [ ] Артефактная проверка через context-mode execute: тесты + `make check` + PR
- [ ] Маркеры: `grep '\[SKILL:' logs/worker-{name}.log` (дополнительно)
- [ ] SDK-CHECK: `grep '\[SDK-CHECK:' logs/worker-{name}.log` — worker проверил реестр?
- [ ] Решение: Code Review OK + артефакты OK → PASS, Code Review FAIL → эскалация
- [ ] **Фаза 5.2:** Orch лично анализирует diff: новые imports, pyproject.toml, новые файлы
- [ ] **Фаза 5.2:** Обновить `.claude/rules/sdk-registry.md` если есть находки (отдельный коммит в dev)
- [ ] `orch_log` записать результат
- [ ] Переименовать сигнал → `done-worker-{name}.json`
- [ ] Очистка: убить окно + удалить worktree

## Чеклист (Фаза 6 — финальный отчёт)

- [ ] Таблица: issue / уровень / контракт / worker / время / стоимость / PR / статус
- [ ] Итого: N issues, N PRs, N эскалаций, ~$X, wall-time
- [ ] Все PR URLs списком
- [ ] `orch-log.jsonl` сохранён
