# SDK-First в tmux-swarm-orchestration — Дизайн

## Проблема

Агенты (orch + workers) не знают какие SDK используются в проекте и как. Результат — кастомный код вместо SDK-решений. Phase 2.7 условная ("если нужно"), воркерам запрещён SDK ресёрч.

## Решение

3 артефакта: SDK-реестр (проектный) + изменения в скилле + изменения в контрактах.

## Артефакт 1: `.claude/rules/sdk-registry.md`

Проектный файл с таблицей всех SDK. Формат каждой записи:

```markdown
## {sdk_name}
triggers: keyword1, keyword2, keyword3
как_у_нас: path/to/usage — краткое описание паттерна
gotchas: антипаттерн → правильный подход
context7_id: /org/project
```

### SDK для rag-fresh (средняя детализация — ключевые):

- **aiogram-dialog** — меню, навигация, виджеты, состояния
- **langgraph** — RAG pipeline, state graph, nodes, edges
- **qdrant-client** — vector search, query_points, prefetch
- **instructor** — structured extraction из LLM
- **redisvl** — semantic cache, search index
- **langfuse** — observability, tracing, decorators

### SDK для rag-fresh (короткая — остальные):

- **aiogram** — bot framework, routers, middlewares, filters
- **langmem** — conversation memory summarization
- **apscheduler** — scheduled jobs
- **fluentogram** — i18n (.ftl файлы)
- **cocoindex** — ingestion pipeline
- **livekit-agents** — voice bot
- **asyncpg** — PostgreSQL

## Артефакт 2: Изменения в `SKILL.md`

### Phase 2.7 → обязательная при наличии реестра

Текущее поведение: "если issue затрагивает SDK/библиотеку" (orch решает субъективно).

Новое поведение:
1. `test -f .claude/rules/sdk-registry.md` — реестр существует?
2. Да → извлечь все `triggers:` из реестра, матчить против issue body
3. Матч найден → Sonnet субагент с `context7_id` из реестра
4. Нет матча → skip полный ресёрч, но `{sdk_registry_excerpt}` всё равно в промт воркера
5. Нет реестра → поведение как раньше (по усмотрению orch)

### `{sdk_registry_excerpt}` — новый placeholder

Orch вставляет в промт воркера релевантные блоки из реестра (только SDK с совпавшими triggers). Воркер видит "как_у_нас" + "gotchas" без полного ресёрча.

## Артефакт 3: Изменения в `worker-contract.md`

### Общие правила — добавить SDK-FIRST

```
SDK-FIRST ПРАВИЛО:
Если задача покрывается SDK из реестра — используй SDK, не пиши кастом.
Проверь {sdk_registry_excerpt} ПЕРЕД написанием кода.
Нашёл SDK решение → используй. Не нашёл → кастом допустим.
```

### Контракты A/B/D — новая секция

```
SDK РЕЕСТР (релевантные записи из .claude/rules/sdk-registry.md):
{sdk_registry_excerpt}
```

Располагается после SDK КОНТЕКСТ, перед HARD-GATE.

### Контракт C — усилить SDK ресёрч

Opus C уже может делать SDK ресёрч. Добавить:
- Обязательно прочитать `.claude/rules/sdk-registry.md`
- В плане — секция "SDK Coverage": какие SDK используются, какие сигнатуры
- Если план предлагает кастом для чего-то что есть в SDK → обосновать почему

## Файлы для изменения

| Файл | Действие |
|------|----------|
| `.claude/rules/sdk-registry.md` | Создать (новый) |
| `~/.claude/skills/tmux-swarm-orchestration/SKILL.md` | Изменить Phase 2.7 |
| `~/.claude/skills/tmux-swarm-orchestration/worker-contract.md` | Изменить контракты |

## Не трогаем

- `classification.md` — классификация сложности не зависит от SDK
- `infrastructure.md` — инфраструктура tmux/worktree не меняется
- `red-flags.md` — можно добавить "wrote custom instead of SDK" позже
