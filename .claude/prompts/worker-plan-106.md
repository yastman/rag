W-P106: Написать план реализации для issue #106 (BGE-M3 cold start + ONNX spike)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 106 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Выполни MCP ресерч (список ниже)
4. Напиши план в docs/plans/2026-02-11-bge-cold-start-plan.md
5. Залогируй результат

Рабочая директория: /repo

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- telegram_bot/integrations/embeddings.py (embedding client)
- services/bge-m3-api/app.py (BGE-M3 API server)
- docker/bge-m3/Dockerfile (Docker image)
- docker-compose.dev.yml (compose config, bge-m3 service)
- telegram_bot/graph/nodes/retrieve.py (retrieve node, embed calls)

MCP TOOLS (обязательно ПЕРЕД написанием плана):
- Exa: web_search_exa("BGE-M3 ONNX INT8 CPU inference cold start optimization 2026")
- Exa: get_code_context_exa("ONNX Runtime BGE-M3 ORTModelForCustomTasks int8 quantization warmup")
- Context7: resolve-library-id(libraryName="optimum", query="ONNX runtime model export INT8") затем query-docs
- Context7: resolve-library-id(libraryName="onnxruntime", query="InferenceSession options CPU optimization") затем query-docs

ФОРМАТ ПЛАНА:
- Заголовок: "# BGE-M3 Cold Start Mitigation + ONNX Spike — Implementation Plan"
- Goal: 1-2 предложения
- Issue: https://github.com/yastman/rag/issues/106
- План ОБЯЗАН включать ДВА этапа:
  Phase A (quick fix, до Gate 1): prewarm при старте + keep-warm ping
  Phase B (ONNX spike, после Gate 1): исследование + POC ORTModelForCustomTasks
- Текущее состояние: таблица файлов с номерами строк
- Шаги реализации: 2-5 минут каждый, точные файлы и строки
- Test Strategy: конкретные тест-файлы
- Acceptance Criteria: измеримые (cold start target < 3s)
- Effort Estimate: S/M/L + часы (отдельно Phase A и Phase B)
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /repo/logs/worker-plan-106.log (APPEND mode):
echo "[START] $(date +%H:%M:%S) Issue #106: BGE cold start plan" >> logs/worker-plan-106.log
... работа ...
echo "[DONE] $(date +%H:%M:%S) Issue #106: plan written" >> logs/worker-plan-106.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-106.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P106 COMPLETE — проверь logs/worker-plan-106.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг плана = конкретный файл + номер строки + что именно менять
4. MCP tools вызывай ПЕРЕД написанием плана
