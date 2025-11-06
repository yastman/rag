# 📋 TODO - Daily Task Tracker

> **Дата создания:** 2025-01-06
> **Последнее обновление:** 2025-01-06 10:00 UTC
> **Текущая фаза:** Phase 1 - Critical Security & Performance

---

## 🎯 Сегодня (2025-01-06)

### 🔥 В работе (In Progress)
*Нет задач в работе*

### ✅ Выполнено сегодня (0/0)
*Пусто*

### ⏰ Запланировано на сегодня
- [ ] **1.1** Ротация API ключей (30 мин) - `@unassigned`
- [ ] **1.3** Создать полный requirements.txt (1 час) - `@unassigned`

---

## 📅 Эта неделя (06-12 Jan 2025)

### 🔴 Critical (Phase 1)
- [ ] **1.1** Security: Ротация API ключей - `30 мин` - 🔴 NOT STARTED
- [ ] **1.2** Performance: requests → httpx - `2 часа` - 🔴 NOT STARTED
- [ ] **1.3** Dependencies: Полный requirements.txt - `1 час` - 🔴 NOT STARTED
- [ ] **1.4** Performance: Fix blocking calls - `2 часа` - 🔴 NOT STARTED

### 🟠 High Priority (Phase 2) - Начать после Phase 1
- [ ] **2.1** Singleton для embedding model - `4 часа` - 🔴 NOT STARTED
- [ ] **2.2** Distributed lock для cache - `3 часа` - 🔴 NOT STARTED
- [ ] **2.3** Rate limiting для bot - `3 часа` - 🔴 NOT STARTED

### Прогресс недели
```
Mon [░░░░░░░░░░] 0% (0/4 Phase 1)
Tue [░░░░░░░░░░] 0%
Wed [░░░░░░░░░░] 0%
Thu [░░░░░░░░░░] 0%
Fri [░░░░░░░░░░] 0%
```

---

## 📊 Статистика

### Общий прогресс
- **Всего задач:** 16
- **Выполнено:** 0 (0%)
- **В работе:** 0
- **Не начато:** 16

### По фазам
```
Phase 1 (Critical):     ░░░░░░░░░░  0% (0/4)
Phase 2 (High):         ░░░░░░░░░░  0% (0/4)
Phase 3 (Medium):       ░░░░░░░░░░  0% (0/4)
Phase 4 (Nice-to-have): ░░░░░░░░░░  0% (0/4)
```

### Velocity (задач/день)
- **Цель:** 1-2 задачи/день (Phase 1-2)
- **Факт:** 0 (данных недостаточно)

---

## 🚧 Блокеры

### Активные блокеры
*Нет блокеров*

### Решенные блокеры
*Пусто*

---

## 💡 Заметки и идеи

### 2025-01-06
- Создана система трекинга задач (ROADMAP.md, CHANGELOG.md, TODO.md)
- Проведен глубокий анализ проекта
- Выявлено 19 критических и важных проблем
- Приоритизировано 16 задач в 4 фазах

### Технические долги
- [ ] Resolve TODOs в `src/evaluation/mlflow_experiments.py`
- [ ] Add type hints для `convert_to_python_types`
- [ ] Remove `n8n` dependency comment в indexer.py

### Улучшения (backlog)
- Implement circuit breaker pattern для external services
- Add request/response logging middleware
- Create admin dashboard для monitoring
- Implement A/B testing framework для cache strategies

---

## 🎯 Цели на неделю (KPIs)

### Технические
- [ ] RAM usage: < 4GB (current: ~6GB)
- [ ] No exposed secrets в репозитории
- [ ] All async methods non-blocking
- [ ] requirements.txt полный и рабочий

### Процессные
- [ ] 100% Phase 1 completion (4/4 задач)
- [ ] 50%+ Phase 2 completion (2+/4 задач)
- [ ] 0 security vulnerabilities
- [ ] Code review для всех PR

---

## 📝 Лог изменений (Quick Log)

### 2025-01-06 10:00
- ✅ Created ROADMAP.md with 16 prioritized tasks
- ✅ Created CHANGELOG.md following Keep a Changelog v1.1.0
- ✅ Created TODO.md (this file)
- ⏳ Waiting for team to start Phase 1

---

## 🔄 Процесс работы

### Начало работы над задачей
1. Выбрать задачу из "Запланировано на сегодня"
2. Переместить в "В работе"
3. Обновить ROADMAP.md (статус → 🟡 IN PROGRESS)
4. Присвоить себя в ROADMAP.md
5. Создать ветку: `git checkout -b feature/1.2-httpx-migration`

### Завершение задачи
1. Тестирование изменений
2. Создать PR с reference на task (e.g., `Closes #1.2`)
3. Обновить TODO.md (переместить в "Выполнено")
4. Обновить ROADMAP.md (статус → ✅ DONE)
5. Обновить CHANGELOG.md (добавить в [Unreleased])

### Ежедневный ритуал (EOD - End of Day)
1. Обновить "Выполнено сегодня"
2. Запланировать задачи на завтра
3. Записать блокеры и заметки
4. Commit: `git commit -m "docs(todo): update daily progress 2025-01-06"`
5. Push: `git push origin main`

---

## 📞 Коммуникация

### Вопросы по задачам
- Открыть issue с label `#task-question`
- Reference task number: "Question about Task 1.2"

### Reporting прогресса
- Daily: Обновить TODO.md
- Weekly: Team sync meeting
- Monthly: Review ROADMAP.md и KPIs

### Эскалация блокеров
1. Добавить в раздел "Блокеры"
2. Notify team lead
3. Create issue с label `#blocker`

---

## 🏷️ Статусы задач

- 🔴 **NOT STARTED** - Задача не начата
- 🟡 **IN PROGRESS** - Задача в работе
- 🟢 **REVIEW** - Задача на ревью (PR created)
- ✅ **DONE** - Задача завершена (PR merged)
- ⚠️ **BLOCKED** - Задача заблокирована
- ❌ **CANCELLED** - Задача отменена

---

## 🎨 Template для новой задачи

```markdown
- [ ] **X.X** Title - `время` - 🔴 NOT STARTED - `@assignee`
  - **Файл:** path/to/file.py
  - **Проблема:** Description
  - **Actions:**
    1. Step 1
    2. Step 2
  - **Blocker:** None
  - **PR:** N/A
```

---

## 🔗 Ссылки

- [ROADMAP.md](./ROADMAP.md) - Полный roadmap с деталями
- [CHANGELOG.md](./CHANGELOG.md) - История изменений
- [README.md](./README.md) - Документация проекта
- [GitHub Issues](https://github.com/yastman/rag/issues) - Issue tracker

---

**Maintained by:** Project Team
**Update frequency:** Daily (EOD)
**Format:** Markdown checklist

---

## 📖 How to Use This File

### Для себя (личный трекинг)
1. Каждое утро: выбрать 1-2 задачи на день
2. В течение дня: обновлять статусы
3. Вечером: заполнить "Выполнено" и план на завтра

### Для команды (team tracking)
1. Все смотрят на "В работе" чтобы избежать дублирования
2. Блокеры видны всем
3. Progress bar показывает общий прогресс

### Автоматизация (будущее)
- GitHub Actions для auto-update из Issues
- Bot для напоминаний в Slack/Telegram
- Auto-generate daily report

---

**Last updated:** 2025-01-06 10:00 UTC
**Next update:** 2025-01-06 EOD
