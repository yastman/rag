# Skill: dependency-updates

**Дата:** 2026-01-28
**Статус:** Draft
**Команда:** `/deps`

## Цель

Интерактивный помощник для работы с Renovate Dashboard — анализирует PR, категоризирует по риску, рекомендует безопасные обновления, выполняет merge с проверкой тестов.

## Workflow

```
/deps
  ↓
Читает: gh pr list --author "renovate[bot]"
  ↓
Категоризирует: Safe → Medium → Risky
  ↓
Показывает рекомендации с эмодзи
  ↓
Ждёт подтверждения: "Merge safe?" / "Какие?"
  ↓
Выполняет: gh pr merge N --squash
  ↓
Запускает: pytest tests/unit/ -q
  ↓
Отчёт: "5 merged, 0 failed, 3 skipped (major)"
```

## Категоризация по риску

### Safe (auto-recommend)
- Patch версии: `1.2.3 → 1.2.4`
- GitHub Actions patch/minor
- Стабильные библиотеки: `pydantic`, `httpx`, `uvicorn`, `python-dotenv`

### Medium (спросить)
- Minor версии: `1.2.0 → 1.3.0`
- Docker образы minor: `qdrant:v1.16 → v1.17`
- ML библиотеки: `torch`, `transformers`, `sentence-transformers`

### Risky (предупредить)
- Major версии: `1.x → 2.x`
- Python base image: `3.12 → 3.14`
- Known breaking: `numpy v2`, `langfuse v3`

## Формат вывода

```
📦 Dependency Updates

✅ SAFE (5 PRs) — рекомендую merge:
   #18 httpx 0.28.1
   #19 prometheus-client 0.24.1
   #21 pydantic-settings 2.12.0

⚠️ MEDIUM (3 PRs) — проверить changelog:
   #13 mlflow v2.22.4
   #24 qdrant-client 1.16.2

❌ RISKY (4 PRs) — не трогать без причины:
   #22 python 3.14 (major)
   #35 numpy v2 (breaking)

Merge safe? [y/n/номера]
```

## Команды

| Ввод | Действие |
|------|----------|
| `y` | Merge все SAFE |
| `n` | Отмена |
| `18,19,21` | Merge конкретные PR |
| `all` | Merge SAFE + MEDIUM |
| `rebase` | `@renovate rebase` для конфликтных |

## После merge

1. Запустить `pytest tests/unit/ -q`
2. Если тесты падают — предложить revert
3. Показать итоговый отчёт

## Структура скилла

```
skills/
└── dependency-updates/
    └── SKILL.md
```

## SKILL.md содержимое

```markdown
---
name: dependency-updates
description: Analyze Renovate PRs, recommend safe updates, merge with test verification
---

# Dependency Updates Skill

## Trigger
Invoke with `/deps` command.

## Steps

### 1. Fetch Renovate PRs
\`\`\`bash
gh pr list --author "renovate[bot]" --json number,title,labels
\`\`\`

### 2. Categorize by Risk

**SAFE (patch):**
- Title contains: `to v1.2.3` where only patch changes
- Labels: `dependencies`

**MEDIUM (minor):**
- Title contains: `to v1.3.0` where minor changes
- Docker tags

**RISKY (major):**
- Title contains: `to v2` or `(major)`
- Known breaking: numpy, langfuse, transformers v5

### 3. Present Recommendations

Show formatted list with emojis:
- ✅ SAFE — recommend merge
- ⚠️ MEDIUM — check changelog
- ❌ RISKY — skip unless needed

### 4. Wait for User Input

Options:
- `y` — merge all SAFE
- `n` — cancel
- `18,19` — merge specific PRs
- `rebase` — request rebase for conflicting

### 5. Execute Merges

For each approved PR:
\`\`\`bash
gh pr merge {number} --squash
\`\`\`

### 6. Run Tests

\`\`\`bash
pytest tests/unit/ -q
\`\`\`

### 7. Report Results

Show summary:
- Merged count
- Failed tests (if any)
- Skipped PRs
```

## Примеры использования

**Пример 1: Обычный апдейт**
```
User: /deps

Claude: 📦 Dependency Updates

✅ SAFE (3 PRs):
   #18 httpx 0.28.1
   #19 prometheus-client 0.24.1

⚠️ MEDIUM (1 PR):
   #13 mlflow v2.22.4

Merge safe? [y/n/номера]

User: y

Claude: Merging #18... ✓
        Merging #19... ✓
        Running tests...

        ✅ All tests passed (42 passed in 3.2s)

        Done: 2 merged, 0 failed
```

**Пример 2: Конфликты**
```
User: /deps

Claude: 📦 Dependency Updates

✅ SAFE (2 PRs):
   #20 pydantic 2.12.5 ⚠️ has conflicts
   #21 pydantic-settings 2.12.0

Merge safe? [y/n/rebase]

User: rebase

Claude: Requesting rebase for #20...
        @renovate rebase sent

        Try again in 2-3 minutes.
```
