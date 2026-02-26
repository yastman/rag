# Worker Templates v5

Reference templates for tmux-swarm-orchestration. Loaded when building prompts.

## Feasibility Triage (Phase 1, только для 5+ issues)

    Task(
        description="Triage: issues #{numbers}",
        prompt="""
        Для каждого issue: gh issue view --json title,body,labels,state
        Изучи кодовую базу (Grep, Read) для проверки актуальности.

        Критерии SKIP:
        - Устарело (уже исправлено в коде)
        - Нечёткое (нет воспроизведения, нет контекста)
        - Высокий риск (breaking change без тестов)
        - Дупликат

        Верни СТРОГО таблицу:
        | Issue | Статус | Сложность | Файлы | Причина |
        Статус: DO / SKIP / STALE
        Сложность: trivial / medium / large
        Файлы: max 3
        Максимум 3 строки на issue.
        """,
        subagent_type="Explore",
        model="haiku"
    )

## Implementation Worker (Phase 4)

    W-{NAME}: {описание}

    РАБОЧАЯ ДИРЕКТОРИЯ: {worktree_absolute_path}
    Ветка: {branch_name} (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ.
    НЕ переходи в другие директории (cd). Работай ТОЛЬКО в worktree.

    ISSUE: #{N} — {title}
    {issue_body_or_summary}

    SKILLS (вызови через Skill tool В ЭТОМ ПОРЯДКЕ):
    1. /executing-plans — ПЕРЕД началом работы
    2. /test-driven-development — при написании ЛЮБОГО кода
    3. /verification-before-completion — ПЕРЕД финальным коммитом

    RESEARCH (перед implementation):
    1. Grep/Read затронутые модули — понять текущий код
    2. Context7: resolve-library-id → query-docs (SDK сигнатуры)
    3. Exa: get_code_context_exa "{topic} {CURRENT_YEAR}" (best practices)
    SDK-FIRST: Кастом — только если SDK не покрывает (запиши ПОЧЕМУ).
    ДАТА: {CURRENT_DATE}. В Exa запросы добавляй год.

    ЗАДАЧИ: {Task N: описание}

    SELF-REVIEW (перед коммитом, обязательно):
    1. ruff check --fix {changed_files}
    2. ruff format {changed_files}
    3. uv run pytest {test_files} -v (ТОЛЬКО затронутые, --lf для упавших)
    4. git diff --cached --stat → проверить что коммитишь

    КОММИТ:
    git add {конкретные файлы, НЕ -A}
    git commit -m "{type}({scope}): {description}

    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

    ЗАПРЕЩЕНО (безусловно):
    - rm -rf, git push --force, git reset --hard
    - Модификация .env, credentials, secrets
    - cd за пределы worktree
    - git checkout другой ветки
    - Установка пакетов не из pyproject.toml
    - pytest tests/ (широко) — только конкретные файлы
    - Спавн субагентов (Task tool запрещён)
    - Баг не по теме → gh issue create, НЕ фиксить

    ПРИ ОШИБКЕ:
    - 1-2 неудачи: retry самостоятельно
    - 3 неудачи подряд на одном шаге:
      echo "[FAILED] {шаг}: {краткое описание}" >> logs/worker-{name}.log
      TMUX="" tmux wait-for -S worker-{name}-done → exit
      НЕ retry бесконечно.

    ЛОГ: logs/worker-{name}.log
    echo "[START] $(date -Iseconds)" >> logs/worker-{name}.log
    echo "[PHASE:research] ..." после начала research
    echo "[PHASE:implement] ..." после начала кода
    echo "[PHASE:test] ..." после начала тестов
    echo "[ERROR] {description}" при ошибках
    echo "[COMPLETE] commit: {sha}" после успеха

    SIGNAL (1 Bash вызов — оркестратор получит instant notification):
    TMUX="" tmux wait-for -S worker-{name}-done

    При FAILED (тот же signal, причина в логе):
    echo "[FAILED] {reason}" >> logs/worker-{name}.log
    TMUX="" tmux wait-for -S worker-{name}-done
