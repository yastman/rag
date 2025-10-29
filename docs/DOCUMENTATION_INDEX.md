# 📚 ДОКУМЕНТАЦИЯ - Contextual RAG v2.0.1

> **Полный указатель документации проекта**

## 🚀 БЫСТРЫЙ СТАРТ (Начните отсюда!)

- **[README.md](../README.md)** - Главная страница проекта (5 минут)
- **[QUICK_START.md](guides/QUICK_START.md)** - Установка и первый поиск (5 минут)
- **[SETUP.md](guides/SETUP.md)** - Полная установка и конфигурация

---

## 📖 ОСНОВНАЯ ДОКУМЕНТАЦИЯ

### 1. СТРУКТУРА И АРХИТЕКТУРА

| Документ | Описание |
|----------|---------|
| **[COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md)** ⭐ | Полная структура проекта (33 файла, все модули) |
| **[README_NEW_STRUCTURE.md](README_NEW_STRUCTURE.md)** | Описание новой архитектуры `src/` |
| **[ARCHITECTURE.md](architecture/ARCHITECTURE.md)** | Системная архитектура и дизайн |
| **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** | Старое описание (ориентир) |

### 2. API СПРАВКА

| Документ | Описание |
|----------|---------|
| **[API_REFERENCE.md](api/API_REFERENCE.md)** ⭐ | Полная API справка всех модулей |
| **[SEARCH_ENGINE_GUIDE.md](implementation/SEARCH_ENGINE_GUIDE.md)** | Детали search engines (Baseline, Hybrid, DBSF) |
| **[CONFIG_GUIDE.md](implementation/CONFIG_GUIDE.md)** | Конфигурация и переменные окружения |

### 3. РЕАЛИЗАЦИЯ И ОПТИМИЗАЦИЯ

| Документ | Описание |
|----------|---------|
| **[OPTIMIZATION_PLAN.md](implementation/OPTIMIZATION_PLAN.md)** | План оптимизации и улучшения |
| **[DBSF_vs_RRF_ANALYSIS.md](implementation/DBSF_vs_RRF_ANALYSIS.md)** | Сравнение методов ранжирования |
| **[MIGRATION_PLAN.md](architecture/MIGRATION_PLAN.md)** | План миграции на новую структуру |

### 4. ОТЧЕТЫ И РЕЗУЛЬТАТЫ

| Документ | Описание |
|----------|---------|
| **[FULL_PROJECT_ANALYSIS.md](reports/FULL_PROJECT_ANALYSIS.md)** | Полный анализ проекта (875 строк) |
| **[PHASE1_COMPLETION_SUMMARY.md](reports/PHASE1_COMPLETION_SUMMARY.md)** | Завершение Phase 1 |
| **[PHASE2_COMPLETION_SUMMARY.md](reports/PHASE2_COMPLETION_SUMMARY.md)** | Завершение Phase 2 |
| **[PHASE3_COMPLETION_SUMMARY.md](reports/PHASE3_COMPLETION_SUMMARY.md)** | Завершение Phase 3 |

---

## 📚 РУКОВОДСТВА ПОЛЬЗОВАТЕЛЯ

### Практические инструкции

| Документ | Назначение |
|----------|-----------|
| **[QUICK_START.md](guides/QUICK_START.md)** | 5-минутный старт |
| **[SETUP.md](guides/SETUP.md)** | Развернутая установка |
| **[CODE_QUALITY.md](guides/CODE_QUALITY.md)** | Стандарты разработки |

### Использование компонентов

| Компонент | Документ |
|-----------|----------|
| **Config** | API_REFERENCE.md → CONFIG API |
| **Contextualization** | API_REFERENCE.md → CONTEXTUALIZATION API |
| **Retrieval/Search** | API_REFERENCE.md → RETRIEVAL API |
| **Ingestion** | API_REFERENCE.md → INGESTION API |
| **Evaluation** | API_REFERENCE.md → EVALUATION API |
| **Core Pipeline** | API_REFERENCE.md → CORE PIPELINE API |

---

## 🎯 НАЙДИ ЧТО ТЕБЕ НУЖНО

### Я хочу...

#### ...начать с нуля
1. Прочитай [README.md](../README.md)
2. Следи [QUICK_START.md](guides/QUICK_START.md)
3. Запусти примеры из [API_REFERENCE.md](api/API_REFERENCE.md)

#### ...понять архитектуру
1. Читай [COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md) - полная структура
2. Смотри [ARCHITECTURE.md](architecture/ARCHITECTURE.md) - системный дизайн
3. Исследуй [README_NEW_STRUCTURE.md](README_NEW_STRUCTURE.md) - модули

#### ...использовать API
1. Откройте [API_REFERENCE.md](api/API_REFERENCE.md)
2. Найдите нужный модуль (Config, Contextualization, Retrieval, etc.)
3. Скопируйте пример кода
4. Адаптируйте для своего случая

#### ...оптимизировать производительность
1. Прочитайте [OPTIMIZATION_PLAN.md](implementation/OPTIMIZATION_PLAN.md)
2. Посмотрите [DBSF_vs_RRF_ANALYSIS.md](implementation/DBSF_vs_RRF_ANALYSIS.md)
3. Используйте DBSF+ColBERT (94.0% Recall@1)

#### ...развивать проект
1. Прочитайте [CODE_QUALITY.md](guides/CODE_QUALITY.md)
2. Изучите [COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md)
3. Смотрите примеры в [API_REFERENCE.md](api/API_REFERENCE.md)

#### ...мониторить эксперименты
1. Читайте [API_REFERENCE.md](api/API_REFERENCE.md) → EVALUATION API
2. Запускайте A/B тесты (src/evaluation/run_ab_test.py)
3. Используйте MLflow (http://localhost:5000)

---

## 🔍 ПО МОДУЛЯМ

### src/config/
- **Файлы**: constants.py, settings.py
- **Документация**: [API_REFERENCE.md](api/API_REFERENCE.md#config-api) | [CONFIG_GUIDE.md](implementation/CONFIG_GUIDE.md)
- **Назначение**: Централізована конфигурация всей системы

### src/contextualization/
- **Файлы**: base.py, claude.py, openai.py, groq.py
- **Документация**: [API_REFERENCE.md](api/API_REFERENCE.md#contextualization-api)
- **Назначение**: LLM-обогащение документов контекстом

### src/retrieval/
- **Файлы**: search_engines.py
- **Документация**: [API_REFERENCE.md](api/API_REFERENCE.md#retrieval-api) | [SEARCH_ENGINE_GUIDE.md](implementation/SEARCH_ENGINE_GUIDE.md)
- **Назначение**: 3 search engines (Baseline, Hybrid RRF, DBSF+ColBERT)

### src/ingestion/
- **Файлы**: pdf_parser.py, chunker.py, indexer.py
- **Документация**: [API_REFERENCE.md](api/API_REFERENCE.md#ingestion-api)
- **Назначение**: Загрузка и индексация документов

### src/evaluation/
- **Файлы**: 12 модулей (metrics, mlflow, langfuse, etc.)
- **Документация**: [API_REFERENCE.md](api/API_REFERENCE.md#evaluation-api)
- **Назначение**: Оценка качества и experiment tracking

### src/core/
- **Файлы**: pipeline.py
- **Документация**: [API_REFERENCE.md](api/API_REFERENCE.md#core-pipeline-api)
- **Назначение**: Главный RAG pipeline (точка входа)

### src/utils/
- **Файлы**: structure_parser.py
- **Документация**: src/utils/
- **Назначение**: Утилиты и помощники

---

## 📊 ПРОИЗВОДИТЕЛЬНОСТЬ

### Поиск (150 тестовых запитів)

| Метрика | Baseline | Hybrid RRF | DBSF+ColBERT |
|---------|----------|-----------|--------------|
| **Recall@1** | 91.3% | 88.7% | **94.0%** ⭐ |
| **NDCG@10** | 0.9619 | 0.9524 | **0.9711** ⭐ |
| **MRR** | 0.9491 | 0.9421 | **0.9636** ⭐ |
| **Latency** | 0.65s | 0.72s | 0.69s |

**Вывод**: Используйте DBSF+ColBERT для лучших результатов!

### Индексация

- PDF Parsing: 2-3 минуты (132 chunks)
- Contextualization: 8-12 мин (Claude, ~$12)
- Indexing: 1-2 минуты
- **Total**: ~15-20 минут

---

## 🛠️ ВЕРСИЯ И СОСТОЯНИЕ

| Параметр | Значение |
|----------|----------|
| **Версия** | 2.0.1 |
| **Python** | ≥3.9 |
| **Статус** | ✅ Production Ready |
| **Код Issues** | 0 (было 499) |
| **Типы** | ✅ MyPy проверено |
| **Лinting** | ✅ Ruff (0 issues) |
| **Документация** | ✅ Полная |

---

## 📞 ПОМОЩЬ И ПОДДЕРЖКА

### Если что-то не работает

1. **Qdrant не доступен**
   ```bash
   docker compose up -d qdrant
   curl http://localhost:6333/health
   ```

2. **API ключ не работает**
   - Проверьте `.env` файл
   - Запустите: `python -c "from src.config import Settings; Settings()"`

3. **Медленный поиск**
   - Используйте DBSF+ColBERT вместо Baseline
   - Увеличьте HNSW ef параметр

### Ресурсы

- **GitHub Issues**: Создавайте issues
- **Примеры кода**: [API_REFERENCE.md](api/API_REFERENCE.md#examples)
- **Исходный код**: Папка `src/`

---

## 🎓 РЕКОМЕНДУЕМЫЙ ПУТЬ ОБУЧЕНИЯ

### День 1: Введение
1. ✅ Прочитайте [README.md](../README.md) (15 мин)
2. ✅ Пройдите [QUICK_START.md](guides/QUICK_START.md) (30 мин)
3. ✅ Запустите первый поиск (15 мин)

### День 2: Архитектура
1. ✅ Изучите [COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md) (45 мин)
2. ✅ Прочитайте [ARCHITECTURE.md](architecture/ARCHITECTURE.md) (30 мин)
3. ✅ Исследуйте модули в `src/` (30 мин)

### День 3: API и практика
1. ✅ Проштудируйте [API_REFERENCE.md](api/API_REFERENCE.md) (1 час)
2. ✅ Запустите примеры кода (30 мин)
3. ✅ Напишите свой скрипт (1 час)

### День 4+: Углубленное изучение
1. ✅ [OPTIMIZATION_PLAN.md](implementation/OPTIMIZATION_PLAN.md) - оптимизация
2. ✅ [CODE_QUALITY.md](guides/CODE_QUALITY.md) - стандарты
3. ✅ [FULL_PROJECT_ANALYSIS.md](reports/FULL_PROJECT_ANALYSIS.md) - полный анализ

---

## 📋 ЧЕКЛИСТ

### Setup
- [ ] Клонирован репозиторий
- [ ] Установлены зависимости (`pip install -e .`)
- [ ] Скопирован `.env.example` в `.env`
- [ ] Заполнены API ключи
- [ ] Запущен Qdrant (`docker compose up -d qdrant`)

### Первый запуск
- [ ] Прочитан QUICK_START.md
- [ ] Выполнены все шаги
- [ ] Первый поиск работает
- [ ] Результаты выглядят корректно

### Разработка
- [ ] Установлены pre-commit hooks
- [ ] Запущены тесты (pytest)
- [ ] Лinting проходит (ruff check)
- [ ] Type checking проходит (mypy)

### Deployment
- [ ] Документация актуальна
- [ ] Все тесты проходят
- [ ] Performance приемлема
- [ ] Код готов к production

---

## 🔄 ОБНОВЛЕНИЯ И ВЕРСИИ

### v2.0.1 (Текущая)
- ✅ Новая архитектура `src/`
- ✅ DBSF+ColBERT поиск
- ✅ MLflow + Langfuse интеграция
- ✅ Полная документация
- ✅ Refactored modules

### v2.0.0
- ✅ Базовая RAG система
- ✅ Несколько search engines
- ✅ Multiple LLM providers

### v3.0.0 (Планируется)
- [ ] Query expansion
- [ ] Semantic caching
- [ ] Graph traversal
- [ ] Web UI dashboard

---

**Last Updated**: October 29, 2025
**Версия**: 2.0.1
**Материал**: Complete
