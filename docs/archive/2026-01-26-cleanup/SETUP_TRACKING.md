# 🚀 Система отслеживания задач - Инструкция по настройке

> **Полная система управления задачами для RAG проекта**
> **Дата:** 2025-01-06
> **Статус:** ✅ Ready to use

---

## 📦 Что создано?

### ✅ Файлы документации

| Файл | Назначение | Обновляется |
|------|-----------|-------------|
| **ROADMAP.md** | Стратегический план с 16 приоритизированными задачами | Еженедельно |
| **CHANGELOG.md** | История изменений (Keep a Changelog format) | При каждом release |
| **TODO.md** | Ежедневный трекинг задач | Ежедневно (EOD) |
| **TASK_MANAGEMENT_2025.md** | Best practices и руководство | По необходимости |
| **SETUP_TRACKING.md** | Этот файл - Quick Start | Один раз |

### ✅ GitHub Actions (CI/CD)

| Workflow | Триггер | Назначение |
|----------|---------|-----------|
| **ci.yml** | push, PR | Lint, Test, Security scan |
| **release.yml** | git tag v*.*.* | Auto-release, Docker build |
| **update-roadmap.yml** | issues, PRs | Auto-update progress |

---

## 🎯 Quick Start (5 минут)

### Шаг 1: Проверить созданные файлы

```bash
cd /mnt/c/Users/user/Documents/Сайты/Раг

# Проверить наличие файлов
ls -la ROADMAP.md CHANGELOG.md TODO.md TASK_MANAGEMENT_2025.md
ls -la .github/workflows/
```

**Ожидаемый результат:**
```
✅ ROADMAP.md (23.5 KB)
✅ CHANGELOG.md (8.2 KB)
✅ TODO.md (6.8 KB)
✅ TASK_MANAGEMENT_2025.md (14.3 KB)
✅ .github/workflows/ci.yml
✅ .github/workflows/release.yml
✅ .github/workflows/update-roadmap.yml
```

### Шаг 2: Закоммитить файлы

```bash
# Add все новые файлы
git add ROADMAP.md CHANGELOG.md TODO.md TASK_MANAGEMENT_2025.md SETUP_TRACKING.md
git add .github/

# Commit с Conventional Commits format
git commit -m "docs(project): add comprehensive task tracking system

- Add ROADMAP.md with 16 prioritized tasks across 4 phases
- Add CHANGELOG.md following Keep a Changelog v1.1.0
- Add TODO.md for daily task tracking
- Add TASK_MANAGEMENT_2025.md with best practices
- Add GitHub Actions workflows (CI, Release, Auto-update)

This establishes a production-ready task management system
following 2025 best practices."

# Push to remote
git push origin main
```

### Шаг 3: Настроить GitHub Actions

```bash
# 1. Enable Actions в GitHub repo settings
# Settings → Actions → General → Allow all actions

# 2. Add secrets (если нужны)
# Settings → Secrets → Actions
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/..."

# 3. Проверить workflows
gh workflow list
gh workflow view ci
```

### Шаг 4: Создать первую задачу

```bash
# Открыть TODO.md и выбрать первую задачу
# Рекомендуется начать с Task 1.1 (Security: API key rotation)

# Update TODO.md
# Переместить Task 1.1 из "Запланировано" в "В работе"

# Update ROADMAP.md
# Изменить статус 1.1 на 🟡 IN PROGRESS
# Добавить assignee: @your-github-username

# Commit changes
git commit -am "docs(tasks): start work on Task 1.1 - API key rotation"
git push
```

---

## 📖 Как использовать систему?

### Ежедневная работа (Daily Workflow)

#### Утро (Morning Routine)

```bash
# 1. Открыть TODO.md
cat TODO.md

# 2. Выбрать 1-2 задачи на сегодня
# Посмотреть "Запланировано на сегодня"

# 3. Переместить в "В работе"
# Edit TODO.md вручную или:
# - [ ] Task X  →  переместить в секцию "В работе"

# 4. Update ROADMAP.md
# Изменить статус задачи на 🟡 IN PROGRESS
# Добавить себя как ответственного

# 5. Создать ветку для работы
git checkout -b feature/1.2-httpx-migration

# 6. Начать работу
code .
```

#### Во время работы (During Development)

```bash
# 1. Commit часто с Conventional Commits
git commit -m "feat(search): replace requests with httpx in HybridRRFSearchEngine"
git commit -m "test(search): add tests for async httpx client"

# 2. Update TODO.md при прогрессе
# Добавлять заметки, блокеры, идеи

# 3. Run pre-commit hooks (автоматически)
git commit  # Ruff, MyPy, etc. запустятся автоматически
```

#### Вечер (End of Day)

```bash
# 1. Update TODO.md
# Переместить завершенные задачи в "Выполнено сегодня"
# - [x] Task 1.1 Security: Ротация API ключей ✅

# 2. Запланировать завтра
# Добавить задачи в "Запланировано на сегодня" для завтра

# 3. Записать заметки
# В разделе "Заметки и идеи"

# 4. Commit progress
git commit -m "docs(todo): daily update 2025-01-06 EOD

Completed:
- Task 1.1: Rotated all API keys
- Updated .env.example

Tomorrow:
- Task 1.2: Migrate to httpx
- Task 1.3: Update requirements.txt"

git push
```

### Еженедельная работа (Weekly Workflow)

#### Пятница вечер (Friday EOD)

```bash
# 1. Review недели в TODO.md
# Заполнить "Прогресс недели"

# 2. Update ROADMAP.md
# Обновить progress bars
# Посчитать velocity

# 3. Team sync meeting
# Обсудить блокеры
# План на следующую неделю

# 4. Commit weekly summary
git commit -m "docs(roadmap): weekly update 2025-01-06

Progress this week:
- Phase 1: 50% complete (2/4 tasks)
- Velocity: 0.4 tasks/day
- Blockers: None

Next week focus:
- Complete Phase 1 (remaining 2 tasks)
- Start Phase 2"
```

### При завершении задачи (Task Completion)

```bash
# 1. Create PR
gh pr create \
  --title "feat(search): replace requests with httpx" \
  --body "Closes #42

## Changes
- Replace requests.post() with httpx.AsyncClient()
- Add timeout configuration (10s)
- Update type hints
- Add tests

## Testing
- [x] Unit tests pass
- [x] Integration tests pass
- [x] Manual testing done

## Checklist
- [x] Code follows style guide
- [x] Tests added
- [x] Documentation updated
- [x] CHANGELOG.md updated

Resolves Task 1.2 from ROADMAP.md"

# 2. Wait for CI to pass
gh pr checks

# 3. Request review
gh pr review --approve

# 4. Merge PR
gh pr merge --squash

# 5. Update tracking files
# TODO.md: переместить в "Выполнено"
# ROADMAP.md: статус → ✅ DONE
# CHANGELOG.md: добавить в [Unreleased]

# 6. Commit tracking updates
git commit -m "docs(tasks): mark Task 1.2 as completed"
```

### При создании release (Release Workflow)

```bash
# 1. Check что все задачи фазы выполнены
# ROADMAP.md: Phase 1 = 100%

# 2. Move changes from [Unreleased] to new version
# Edit CHANGELOG.md:
# [Unreleased] → [2.6.0] - 2025-01-08

# 3. Update version в коде (если есть __version__)
echo '__version__ = "2.6.0"' > src/__version__.py

# 4. Commit release
git commit -m "chore(release): prepare v2.6.0 release"

# 5. Create tag
git tag -a v2.6.0 -m "Release v2.6.0 - Critical Security & Performance Fixes

Highlights:
- Security: Rotated all API keys
- Performance: Migrated to httpx (non-blocking)
- Dependencies: Complete requirements.txt
- Performance: Fixed async blocking calls

See CHANGELOG.md for full details."

# 6. Push tag (triggers release.yml workflow)
git push --tags

# 7. GitHub Actions will:
#    - Build Docker image
#    - Create GitHub Release
#    - Deploy to staging
#    - Send notifications
```

---

## 🤖 Автоматизация

### Что происходит автоматически?

#### 1. При каждом push/PR → ci.yml

```yaml
Запускается:
  1. 🎨 Lint (Ruff)
  2. 🧪 Tests (Pytest)
  3. 🔒 Security scan (Trivy, Bandit)
  4. 🏗️ Build check

Результат:
  ✅ Pass → можно мерджить
  ❌ Fail → нужно исправить
```

#### 2. При создании git tag → release.yml

```yaml
Запускается:
  1. 🏷️ Validate version (есть ли в CHANGELOG)
  2. 🐳 Build Docker image → ghcr.io
  3. 📝 Create GitHub Release (from CHANGELOG)
  4. 🚀 Deploy to staging
  5. 📢 Send notifications (Slack)

Результат:
  - Docker image: ghcr.io/username/rag:v2.6.0
  - GitHub Release: v2.6.0 с notes
  - Staging deployed
```

#### 3. При работе с issues/PRs → update-roadmap.yml

```yaml
Запускается:
  1. 📊 Count tasks (total, done)
  2. 🔢 Calculate progress %
  3. 📝 Update ROADMAP.md progress bars
  4. 🏷️ Auto-label issues (phase-1, critical, etc.)
  5. ✅ Commit changes

Результат:
  - ROADMAP.md auto-updated
  - Issues auto-labeled
```

---

## 🔧 Настройка интеграций

### GitHub

```bash
# 1. Enable Actions
# Repository → Settings → Actions → General
# ✅ Allow all actions and reusable workflows

# 2. Branch protection (optional)
# Settings → Branches → Add rule
# Branch name pattern: main
# ✅ Require status checks (CI must pass)
# ✅ Require pull request reviews (1 approval)

# 3. Add secrets (if needed)
gh secret set CODECOV_TOKEN --body "xxx"
gh secret set SLACK_WEBHOOK_URL --body "xxx"
```

### Pre-commit hooks (Local)

```bash
# 1. Install pre-commit
pip install pre-commit

# 2. Install hooks
pre-commit install

# 3. Test
pre-commit run --all-files

# Now hooks run automatically on git commit
```

### VS Code

```json
// .vscode/settings.json
{
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  },
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff"
  },
  "todo-tree.general.tags": [
    "TODO",
    "FIXME",
    "[ ]",
    "[x]"
  ],
  "todo-tree.highlights.customHighlight": {
    "[ ]": {
      "icon": "checkbox",
      "type": "text"
    },
    "[x]": {
      "icon": "check",
      "type": "text"
    }
  }
}
```

---

## 📊 Метрики и отчеты

### Автоматические отчеты

```bash
# 1. CI Pipeline Summary
# Каждый PR показывает: Lint ✅ Test ✅ Security ✅

# 2. Coverage Report
# Артефакт в GitHub Actions: htmlcov/

# 3. Roadmap Progress
# Автоматически обновляется в ROADMAP.md

# 4. CHANGELOG
# Автоматически генерируется из commits:
conventional-changelog -p angular -i CHANGELOG.md -s
```

### Ручные отчеты

```bash
# Weekly Progress Report
cat TODO.md | grep "Выполнено" | wc -l  # Сколько задач сделано

# Velocity calculation
# Выполнено задач / Дней = задач/день

# Phase progress
# Phase X: Done/Total = %
```

---

## ❓ FAQ

### Q: Как добавить новую задачу?

```bash
# 1. Открыть ROADMAP.md
# 2. Добавить в соответствующую фазу:

- [ ] **X.Y** Title - `время` - 🔴 NOT STARTED - `@unassigned`
  - **Файл:** path/to/file
  - **Проблема:** Description
  - **Действия:**
    1. Step 1
  - **Статус:** 🔴 NOT STARTED

# 3. Commit
git commit -m "docs(roadmap): add new task X.Y"
```

### Q: Как отменить задачу?

```bash
# 1. ROADMAP.md: статус → ❌ CANCELLED
# 2. Добавить причину в комментарий
# 3. TODO.md: удалить из списков
# 4. Commit с объяснением
```

### Q: Как изменить приоритет задачи?

```bash
# 1. Переместить задачу в другую фазу
# 2. Обновить priority emoji (🔴→🟠→🟡→🟢)
# 3. Commit изменений
```

### Q: Как работать в команде?

```bash
# 1. Каждый назначает себя на задачи (@username)
# 2. Избегаем дублирования (смотрим "В работе")
# 3. Ежедневно обновляем TODO.md
# 4. Weekly sync для координации
```

### Q: GitHub Actions не запускается?

```bash
# Check:
1. Settings → Actions → Enabled?
2. Workflow файлы синтаксически корректны?
3. Branch protection правила не блокируют?

# Debug:
gh workflow list
gh run list
gh run view <run-id> --log
```

---

## 🎓 Обучение команды

### Onboarding нового разработчика

```bash
# 1. Read документацию (30 мин)
- README.md
- ROADMAP.md
- TASK_MANAGEMENT_2025.md (this file)

# 2. Setup environment (1 час)
git clone https://github.com/username/rag
cd rag
pip install -r requirements.txt
pre-commit install

# 3. Pick первая задача (легкая)
- Выбрать P3 задачу
- Следовать workflow из TODO.md

# 4. Create первый PR
- Conventional Commits
- Tests included
- Request review

# 5. Team введение
- Weekly sync meeting
- Slack/Discord channel
- Question? → GitHub Discussions
```

---

## 🔗 Полезные ссылки

### Документация проекта
- [ROADMAP.md](./ROADMAP.md) - Стратегический план
- [CHANGELOG.md](./CHANGELOG.md) - История изменений
- [TODO.md](./TODO.md) - Ежедневные задачи
- [TASK_MANAGEMENT_2025.md](./TASK_MANAGEMENT_2025.md) - Best practices

### External
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
- [Semantic Versioning](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Pre-commit](https://pre-commit.com/)

---

## ✅ Checklist: Система настроена?

Проверьте что всё готово:

- [ ] ✅ ROADMAP.md создан и закоммичен
- [ ] ✅ CHANGELOG.md создан и закоммичен
- [ ] ✅ TODO.md создан и закоммичен
- [ ] ✅ TASK_MANAGEMENT_2025.md создан
- [ ] ✅ .github/workflows/ созданы (3 файла)
- [ ] ✅ Files pushed to GitHub
- [ ] ✅ GitHub Actions enabled
- [ ] ✅ Pre-commit hooks installed locally
- [ ] ✅ Team onboarded (если команда есть)
- [ ] ✅ Первая задача выбрана и в работе

**Если все ✅ — система готова к использованию!**

---

## 🎉 Следующие шаги

### Немедленно (Сегодня)
1. ✅ Закоммитить все файлы в git
2. ✅ Включить GitHub Actions
3. 🔴 **Начать Task 1.1** - Ротация API ключей (CRITICAL!)

### Эта неделя
4. Завершить Phase 1 (4 critical tasks)
5. Setup pre-commit hooks локально
6. Провести первый weekly review

### Этот месяц
7. Завершить Phase 1-2 (8 tasks total)
8. Setup monitoring dashboards
9. Провести team retrospective

---

**Система готова! Удачи в разработке! 🚀**

---

**Created:** 2025-01-06
**Last updated:** 2025-01-06
**Maintained by:** Project Team
**Questions?** Create issue с label `#task-management`
