# Контракты воркеров v9

Orch заполняет `{...}` → сохраняет в `.claude/prompts/worker-{name}.md`.

## Общие правила

Включаются в КАЖДЫЙ промт. Не дублируй.

    РАБОЧАЯ ДИРЕКТОРИЯ: {worktree_or_project_root}

    SANDBOX:
    - Доступ ТОЛЬКО к {worktree_or_project_root} и {PROJECT_ROOT}/.signals/
    - Любые пути вне этих директорий → ЗАПРЕЩЕНО
    - Чтение .env, ~/.ssh, ~/.aws, ~/.config/gh → ЗАПРЕЩЕНО
    - pip install, npm install, curl | bash, wget → ЗАПРЕЩЕНО
    - rm -rf, git push --force, git reset --hard → ЗАПРЕЩЕНО
    - git checkout другой ветки → ЗАПРЕЩЕНО
    - pytest tests/ (широко) — только конкретные файлы
    - Спавн субагентов (Agent tool) → ЗАПРЕЩЕНО
    - SDK исследование (Context7/Exa) → ЗАПРЕЩЕНО для A/B/D (orch уже сделал). Разрешено ТОЛЬКО для C.

    ПРИ ОШИБКЕ:
    Skill(skill="systematic-debugging") — структурная отладка, НЕ слепой повтор.
    echo "[SKILL:debugging]" >> logs/worker-{name}.log
    3 неудачи подряд → Сигнал FAILED.

    ЛОГ: logs/worker-{name}.log
    echo "[SKILL:{name}]" при каждом вызове Skill tool

    ПРОГРЕСС (для задач >10 мин):
    echo "[PROGRESS:50%] {что сделано}" >> logs/worker-{name}.log

    СИГНАЛ ЗАВЕРШЕНИЯ (атомарный — write .tmp → mv):
    echo '{"status":"done","worker":"W-{NAME}","pr":"{url}","ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

    СИГНАЛ ПРОВАЛА:
    echo '{"status":"failed","worker":"W-{NAME}","error":"{msg}","ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

---

## Общий финал (контракты A/B/D — код)

Применяется после прохождения всех HARD-GATE скиллов. Не дублируй в контрактах.

    git add {файлы}
    git diff --cached --stat
    git commit -m "$(cat <<'EOF'
    {type}({scope}): {desc}

    Closes #{N}

    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
    EOF
    )"
    git push -u origin {branch_name}
    gh pr create --title "{type}({scope}): {desc}" --body "Closes #{N}"

    # Атомарный сигнал:
    PR_URL=$(gh pr view --json url -q .url)
    echo '{"status":"done","worker":"W-{NAME}","pr":"'"$PR_URL"'","ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

---

## Финал part-worker (контракт B-part — параллельная часть)

Part-workers коммитят и пушат, но **НЕ создают PR**. PR создаёт только финальный worker.

    git add {файлы}
    git diff --cached --stat
    git commit -m "$(cat <<'EOF'
    {type}({scope}): {desc} (part {N})

    Part of #{issue_N}

    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
    EOF
    )"
    git push -u origin {branch_name}

    # Атомарный сигнал (без pr, с branch):
    echo '{"status":"done","worker":"W-{NAME}","branch":"'"${branch_name}"'","ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

---

## SDK исследование субагентом (Фаза 2.7 — orch, НЕ worker)

    Agent(
        description="SDK исследование для #{N}: {library}",
        prompt="""
        Context7: resolve-library-id("{library}") → query-docs("{topic}")
        Exa: get_code_context_exa("{library} {topic} 2026")

        РЕЗУЛЬТАТ:
        А) Резюме (верни мне, макс 300 слов): ключевые сигнатуры, подход, SDK покрывает? ДА/НЕТ
        Б) Полный контекст (Write → .claude/cache/sdk-{library}-{N}.md):
           все сигнатуры, примеры, лучшие практики, анти-паттерны
        """,
        subagent_type="general-purpose",
        model="sonnet"
    )

## Codebase контекст (Фаза 2.3 — orch, НЕ worker)

Orch использует 3 системы ДО классификации для понимания scope и зависимостей:

    # 1. GrepAI — semantic search + call graph:
    grepai_search(query="{issue_description}", limit=5, format="toon", compact=true)
    grepai_trace_callers(symbol="{function_from_issue}", format="toon", compact=true)
    grepai_trace_callees(symbol="{function_from_issue}", format="toon", compact=true)
    grepai_trace_graph(symbol="{key_symbol}", depth=1, format="toon")

    # 2. LSP — точные типы и references:
    LSP(operation="documentSymbol", filePath="{file}")
    LSP(operation="findReferences", filePath="{file}", line=N, character=M)
    LSP(operation="incomingCalls", filePath="{file}", line=N, character=M)

    # 3. context-mode — сбор контекста:
    batch_execute(commands=[...], queries=[...])

Результаты используются для:
- Классификации сложности (Phase 2) — сколько файлов/зависимостей затронуто
- File overlap detection (Phase 2.5) — LSP findReferences точнее, чем grep
- Файловых резерваций — кто владеет какими файлами
- Промта worker'а — добавить `{codebase_context}` с ключевыми находками

---

## Предварительная фильтрация (5+ issues)

Haiku НЕ классифицирует сложность — только фильтрует актуальность.
Сложность определяет orch (Phase 2) после фильтрации.

    Agent(description="Фильтрация #{numbers}", model="haiku", subagent_type="Explore",
      prompt="""
      gh issue view для каждого issue из списка: {numbers}

      КОНТЕКСТ ПРОЕКТА (для определения скоупа):
      {project_scope}

      Для каждого определи ТОЛЬКО статус актуальности:
      - DO — issue актуален, нужно решать
      - SKIP — дубликат другого issue ИЛИ явно закрыт/решён (PR смержен)
      - STALE — устарел (>90 дней без активности, упоминает удалённый код)
      - UNCERTAIN — не уверен в статусе (непонятный скоуп, неясно дубликат ли)

      ПРАВИЛА:
      - Сомневаешься → UNCERTAIN (НЕ SKIP)
      - "Вне скоупа" → UNCERTAIN (ты не знаешь весь скоуп)
      - SKIP только при ЯВНОМ доказательстве (ссылка на PR, дубль номера)

      Верни таблицу:
      | Issue | Статус | Затронутые файлы (из тела issue) | Причина статуса |

      НЕ оценивай сложность. НЕ предлагай решение. Только фильтрация.
      """)

---

## Контракт A: Sonnet реализация

**Когда:** TRIVIAL / CLEAR / MEDIUM — worker получает issue и делает.

    Ты — Sonnet worker. Реши issue и создай PR.

    ISSUE: #{N} — {title}
    {issue_body}

    {Общие правила}
    Ветка: {branch_name} в {worktree_path}. НЕ ПЕРЕКЛЮЧАЙСЯ.

    SDK КОНТЕКСТ (если есть):
    {sdk_summary}
    Полная документация: Read .claude/cache/sdk-{library}-{N}.md

    КОНТРАКТ ИНТЕРФЕЙСА (если параллельная работа):
    {interface_contract}

    ЗАРЕЗЕРВИРОВАННЫЕ ФАЙЛЫ (только ты их редактируешь):
    {reserved_files}

    <HARD-GATE>
    Skill(skill="test-driven-development") — ПЕРЕД кодом. БЕЗ ИСКЛЮЧЕНИЙ.
    Skill(skill="requesting-code-review") — ПЕРЕД коммитом.
    Skill(skill="verification-before-completion") — ПЕРЕД PR.
    Нарушил порядок = провал задачи.
    </HARD-GATE>

    После верификации: {Общий финал}

---

## Контракт B: Sonnet выполнение плана

**Когда:** COMPLEX / VERY COMPLEX — worker получает готовый план от Opus.

    Ты — Sonnet worker. Выполни план и создай PR.

    ISSUE: #{N} — {title}
    ПЛАН: Read {plan_file_path}

    {Общие правила}
    Ветка: {branch_name} в {worktree_path}. НЕ ПЕРЕКЛЮЧАЙСЯ.

    SDK КОНТЕКСТ (если есть):
    {sdk_summary}
    Полная документация: Read .claude/cache/sdk-{library}-{N}.md

    ЗАРЕЗЕРВИРОВАННЫЕ ФАЙЛЫ (только ты их редактируешь):
    {reserved_files}

    <HARD-GATE>
    Skill(skill="executing-plans") — загрузи план, задача за задачей.
    Skill(skill="test-driven-development") — для каждой задачи.
    Skill(skill="requesting-code-review") — ПЕРЕД коммитом.
    Skill(skill="verification-before-completion") — ПЕРЕД PR.
    </HARD-GATE>

    После верификации: {Общий финал}

---

## Контракт C: Opus исследование

**Когда:** COMPLEX / VERY COMPLEX — исследование + план, БЕЗ кода.

    Ты — Opus research worker. Изучи проблему и напиши план. НЕ КОДЬ.

    ISSUE: #{N} — {title}
    {issue_body}

    {Общие правила}
    Ветка: main. НЕ создавай веток.

    SDK КОНТЕКСТ (если есть):
    {sdk_summary}
    Полная документация: Read .claude/cache/sdk-{library}-{N}.md
    Углуби SDK исследование если нужно (Context7, Exa). Включи SDK контекст в план.

    CODEBASE КОНТЕКСТ (3 системы — ИСПОЛЬЗУЙ ВСЕ):

    GrepAI MCP (semantic search + call graph):
    - grepai_search(query="...", format="toon", compact=true) — найти код по описанию
    - grepai_trace_callers(symbol="...", format="toon") — кто вызывает
    - grepai_trace_callees(symbol="...", format="toon") — что вызывает
    - grepai_trace_graph(symbol="...", depth=1, format="toon") — полный call graph

    LSP (точные типы, сигнатуры, структура):
    - LSP documentSymbol(filePath) — все символы файла (классы, методы)
    - LSP hover(filePath, line, char) — тип + docstring символа
    - LSP findReferences(filePath, line, char) — все ссылки на символ
    - LSP incomingCalls(filePath, line, char) — кто вызывает метод

    context-mode (экономия контекста для больших файлов):
    - execute_file(path, language, code) — анализ файла без загрузки в контекст
    - batch_execute(commands, queries) — N команд + поиск в одном вызове
    Используй вместо Read для файлов >50 строк. Вместо Bash для output >20 строк.

    <HARD-GATE>
    Skill(skill="writing-plans") — для создания плана. БЕЗ ИСКЛЮЧЕНИЙ.
    </HARD-GATE>

    План → docs/plans/{DATE}-issue-{N}-plan.md
    План содержит: файлы, подход, SDK сигнатуры, задачи по 2-5 мин, TDD.
    ЗАПРЕЩЕНО: production код, создание веток.

    ## РЕШЕНИЕ О ВЫПОЛНЕНИИ

    После составления плана — оцени задачи и реши:

    EXECUTION: sequential | parallel

    **sequential** (по умолчанию) — если:
    - Задачи образуют цепочку зависимостей (модель → сервис → API)
    - Большинство задач трогают общие файлы
    - <7 задач (overhead параллелизации не окупится)

    **parallel** — если ВСЕ условия выполнены:
    - ≥3 задачи без зависимостей друг от друга
    - Задачи трогают РАЗНЫЕ файлы (нет пересечений)
    - Каждая группа самодостаточна (свой код + свои тесты)

    При parallel — план ОБЯЗАН содержать секцию:

    ## Группы выполнения
    ### Группа A (worker-1): задачи 1, 3, 5
    Файлы: src/models/user.py, tests/test_user.py
    ### Группа B (worker-2): задачи 2, 4
    Файлы: src/services/cache.py, tests/test_cache.py
    ### Группа C (финальная, после A+B): задачи 6, 7
    Файлы: src/api/routes.py, tests/test_api.py
    Зависит от: A, B

    Правила группировки:
    - Файлы НЕ пересекаются между группами
    - Зависимая группа запускается ПОСЛЕ тех, от кого зависит
    - Финальная группа (интеграция, документация) — всегда последняя

    # Атомарный сигнал — включить execution решение:
    echo '{"status":"done","worker":"W-{NAME}","plan":"{path}","execution":"{sequential|parallel}","groups":{N},"ts":"'$(date -Iseconds)'"}' \
      > ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp \
      && mv ${PROJECT_ROOT}/.signals/worker-{name}.json.tmp ${PROJECT_ROOT}/.signals/worker-{name}.json

---

## Контракт D: Opus соло

**Когда:** VERY COMPLEX — Sonnet не потянет. Полный цикл.

    Ты — Opus solo worker. Изучи, спланируй, реализуй, создай PR.

    ISSUE: #{N} — {title}
    {issue_body}

    {Общие правила}
    Ветка: {branch_name} в {worktree_path}. НЕ ПЕРЕКЛЮЧАЙСЯ.

    SDK КОНТЕКСТ (если есть):
    {sdk_summary}
    Полная документация: Read .claude/cache/sdk-{library}-{N}.md

    <HARD-GATE>
    Skill(skill="writing-plans") → Skill(skill="executing-plans") →
    Skill(skill="test-driven-development") → Skill(skill="requesting-code-review") →
    Skill(skill="verification-before-completion")
    Все 5 скиллов ОБЯЗАТЕЛЬНЫ. Нарушил = провал.
    </HARD-GATE>

    После верификации: {Общий финал}
