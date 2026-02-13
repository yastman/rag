W-TRIAGE: Backlog audit and issue triage (Issue #175)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — финальная проверка

MCP TOOLS (используй для исследования):
- Exa: web_search_exa("github issue triage best practices 2026 backlog management") для свежих паттернов
- Exa: web_search_exa("github cli gh issue bulk operations labels priorities") для gh CLI tricks

КОНТЕКСТ:
Issue #175: backlog audit v2 — review all open issues, dedupe, reprioritize.
Уже сделано: первый triage pass (комментарий в #175 с решениями по каждому issue).
Подтверждено код-ревью: #155, #164, #166, #167, #168 — реально сломаны/открыты.
#174 уже закрыт как дуп #166.

Приоритетный порядок из triage:
1. #71 (epic)
2. #164 (chaos tests)
3. #166 (validation retry)
4. #167 (baseline contamination)
5. #168 (validation thresholds)
6. #155 (redisvl vectorizer)
7. #162 (SDK hooks)
8. #147 (latency dashboards)

РАБОЧАЯ ДИРЕКТОРИЯ: /home/user/projects/rag-w/triage
ВЕТКА: chore/parallel-backlog/triage-175 (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ФАЗА 1 — ИССЛЕДОВАНИЕ И ПЛАН:
1. Исследуй через Exa: best practices для GitHub issue triage, labeling strategy
2. Выгрузи все open issues: gh issue list --state open --json number,title,labels,assignees,milestone --limit 100
3. Выгрузи все open PRs: gh pr list --state open --json number,title,headRefName,labels --limit 20
4. Сопоставь PRs с issues (какие issues уже имеют PR)
5. Напиши план в docs/plans/2026-02-12-triage-execution-plan.md

ФАЗА 2 — ВЫПОЛНЕНИЕ:
1. Для каждого open issue определи:
   - Статус: has-PR / in-progress / needs-work / stale / duplicate
   - Приоритет: P0 (blocking) / P1 (next) / P2 (backlog) / P3 (idea)
2. Обнови labels на issues (создай labels если не существуют):
   - gh label create "P0-critical" --color "d73a4a" (если не существует)
   - gh label create "P1-next" --color "e4e669" (если не существует)
   - gh label create "P2-backlog" --color "0075ca" (если не существует)
   - gh label create "has-pr" --color "a2eeef" (если не существует)
3. Проставь labels на каждый issue
4. Закрой очевидные дупликаты с комментарием (duplicate of #XX)
5. Добавь acceptance criteria в issues которые его не имеют
6. Напиши итоговый отчёт в docs/reports/2026-02-12-triage-results.md с таблицей
7. Коммит отчёт + план

ПРАВИЛА:
1. НЕ закрывай issues без уверенности что это дупликат или resolved
2. НЕ удаляй existing labels, только добавляй
3. Каждое закрытие — с комментарием-объяснением
4. git commit — ТОЛЬКО конкретные файлы docs/. ЗАПРЕЩЕНО git add -A
5. ПЕРЕД коммитом: git diff --cached --stat
6. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-triage.log (APPEND):
Формат: echo "[START/DONE] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-triage.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker triage finished" >> /home/user/projects/rag-fresh/logs/worker-triage.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-TRIAGE COMPLETE — проверь logs/worker-triage.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
