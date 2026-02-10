W-LATENCY: Latency Remediation — КОНКРЕТНЫЕ ПРАВКИ

Работай из /repo.

АНТИГАЛЛЮЦИНАЦИЯ:
- НЕ пиши "ALREADY DONE" — проверяй файлы через Read tool ПЕРЕД любым выводом
- Каждую правку делай через Edit tool с exact old_string → new_string
- После каждого Edit запускай Bash с grep чтобы ПОДТВЕРДИТЬ что изменение прошло
- Если grep показывает старое значение — правка НЕ прошла, повтори

НЕ ТРОГАЙ: .github/workflows/ci.yml, pyproject.toml, scripts/monitor-workers.sh, telegram_bot/observability.py

MCP TOOLS:
- Context7: resolve-library-id → query-docs для SDK документации LangGraph/Langfuse
- Exa: web_search_exa / get_code_context_exa для примеров и best practices

== ПРАВКА 1: telegram_bot/graph/config.py ==

Edit 1a:
old_string: "max_rewrite_attempts: int = 2"
new_string: "max_rewrite_attempts: int = 1"

Edit 1b:
old_string: "rewrite_max_tokens: int = 200"
new_string: "rewrite_max_tokens: int = 64"

Edit 1c: в from_env() добавить max_rewrite_attempts после domain_language:
old_string: "domain_language=os.getenv(\"BOT_LANGUAGE\", \"ru\"),"
new_string: "domain_language=os.getenv(\"BOT_LANGUAGE\", \"ru\"),\n            max_rewrite_attempts=int(os.getenv(\"MAX_REWRITE_ATTEMPTS\", \"1\")),"

Edit 1d:
old_string: "rewrite_max_tokens=int(os.getenv(\"REWRITE_MAX_TOKENS\", \"200\")),"
new_string: "rewrite_max_tokens=int(os.getenv(\"REWRITE_MAX_TOKENS\", \"64\")),"

VERIFY: grep -n "max_rewrite_attempts" telegram_bot/graph/config.py
EXPECT: "= 1" (НЕ "= 2")
VERIFY: grep -n "rewrite_max_tokens" telegram_bot/graph/config.py
EXPECT: "= 64" (НЕ "= 200")

== ПРАВКА 2: telegram_bot/graph/state.py ==

Edit 2a: добавить поле в RAGState:
old_string: "    rerank_applied: bool"
new_string: "    rerank_applied: bool\n    max_rewrite_attempts: int"

Edit 2b: изменить сигнатуру:
old_string: "def make_initial_state(user_id: int, session_id: str, query: str) -> dict[str, Any]:"
new_string: "def make_initial_state(\n    user_id: int, session_id: str, query: str, *, max_rewrite_attempts: int = 1\n) -> dict[str, Any]:"

Edit 2c: добавить в dict:
old_string: "        \"rerank_applied\": False,"
new_string: "        \"rerank_applied\": False,\n        \"max_rewrite_attempts\": max_rewrite_attempts,"

VERIFY: grep -n "max_rewrite_attempts" telegram_bot/graph/state.py
EXPECT: 3 совпадения

== ПРАВКА 3: telegram_bot/graph/edges.py ==

Edit 3a:
old_string: "    if state.get(\"rewrite_count\", 0) < 2 and state.get(\"rewrite_effective\", True):"
new_string: "    max_attempts = state.get(\"max_rewrite_attempts\", 1)\n    if state.get(\"rewrite_count\", 0) < max_attempts and state.get(\"rewrite_effective\", True):"

VERIFY: grep -n "max_attempts" telegram_bot/graph/edges.py
EXPECT: 2 совпадения

== ПРАВКА 4: telegram_bot/bot.py ==

Edit 4a:
old_string: "        state = make_initial_state(\n            user_id=message.from_user.id,\n            session_id=make_session_id(\"chat\", message.chat.id),\n            query=message.text or \"\",\n        )"
new_string: "        state = make_initial_state(\n            user_id=message.from_user.id,\n            session_id=make_session_id(\"chat\", message.chat.id),\n            query=message.text or \"\",\n            max_rewrite_attempts=self._graph_config.max_rewrite_attempts,\n        )"

VERIFY: grep -n "max_rewrite_attempts" telegram_bot/bot.py
EXPECT: 1 совпадение

== ПРАВКА 5: tests/unit/graph/test_config.py ==

Edit 5a:
old_string: "assert cfg.max_rewrite_attempts == 2"
new_string: "assert cfg.max_rewrite_attempts == 1"

Edit 5b: добавить новые тесты в конец класса TestGraphConfig (перед последней строкой файла):
Добавь 5 тестов: test_from_env_reads_max_rewrite_attempts, test_from_env_default_max_rewrite_attempts, test_default_rewrite_max_tokens_is_64, test_from_env_reads_rewrite_max_tokens, test_from_env_default_rewrite_max_tokens.
Каждый тест импортирует GraphConfig, использует patch.dict(os.environ, ..., clear=True).

== ПРАВКА 6: tests/unit/graph/test_state.py ==

Edit 6a: добавить max_rewrite_attempts в required list:
old_string: "            \"rerank_applied\","
new_string: "            \"rerank_applied\",\n            \"max_rewrite_attempts\","

Edit 6b: добавить 2 теста в конец класса.

== ПРАВКА 7: tests/unit/graph/test_edges.py ==

Edit 7a: тест test_not_relevant_second_attempt_routes_to_rewrite теперь даёт "generate" (default max=1, count=1):
old_string: "    def test_not_relevant_second_attempt_routes_to_rewrite(self):\n        state = make_initial_state(user_id=1, session_id=\"s\", query=\"test\")\n        state[\"documents_relevant\"] = False\n        state[\"rewrite_count\"] = 1\n        assert route_grade(state) == \"rewrite\""
new_string: "    def test_not_relevant_second_attempt_routes_to_generate(self):\n        \"\"\"With default max_rewrite_attempts=1, rewrite_count=1 goes to generate.\"\"\"\n        state = make_initial_state(user_id=1, session_id=\"s\", query=\"test\")\n        state[\"documents_relevant\"] = False\n        state[\"rewrite_count\"] = 1\n        assert route_grade(state) == \"generate\""

Edit 7b: тест test_route_grade_rewrite_effective_allows_retry — добавить max_rewrite_attempts=2:
old_string: "        state = {\n            \"documents_relevant\": False,\n            \"rewrite_count\": 1,\n            \"rewrite_effective\": True,\n        }\n        assert route_grade(state) == \"rewrite\""
new_string: "        state = {\n            \"documents_relevant\": False,\n            \"rewrite_count\": 1,\n            \"rewrite_effective\": True,\n            \"max_rewrite_attempts\": 2,\n        }\n        assert route_grade(state) == \"rewrite\""

Edit 7c: добавить 3 новых теста для max_rewrite_attempts в конец класса TestRouteGrade.

== ПРАВКА 8: docker-compose.dev.yml ==

Прочитай файл, найди bot service environment секцию. Добавь 3 строки env vars:
      MAX_REWRITE_ATTEMPTS: "${MAX_REWRITE_ATTEMPTS:-1}"
      REWRITE_MAX_TOKENS: "${REWRITE_MAX_TOKENS:-64}"
      BGE_M3_TIMEOUT: "${BGE_M3_TIMEOUT:-30}"

== КОММИТ ==

git add telegram_bot/graph/config.py telegram_bot/graph/state.py telegram_bot/graph/edges.py telegram_bot/bot.py tests/unit/graph/test_config.py tests/unit/graph/test_state.py tests/unit/graph/test_edges.py docker-compose.dev.yml

Коммит (используй heredoc):
git commit -m "$(cat <<'EOF'
feat(latency): wire configurable rewrite limits and token budget

- max_rewrite_attempts: env-configurable, default 2->1
- rewrite_max_tokens: default 200->64
- route_grade reads max_rewrite_attempts from state
- docker-compose runtime knobs

Refs: #97, #98, #99, #100

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"

== ТЕСТЫ ==

uv run pytest tests/unit/graph/ -v
uv run ruff check telegram_bot/graph/ tests/unit/graph/
uv run ruff format --check telegram_bot/graph/ tests/unit/graph/

Если тесты падают — фикси и перезапускай. НЕ коммить если тесты красные.

== ЛОГИРОВАНИЕ ==

echo "[START] $(date +%H:%M:%S) Latency remediation" >> /repo/logs/worker-latency.log
... после каждой правки echo "[DONE] ..." ...
echo "[COMPLETE] $(date +%H:%M:%S) All done" >> /repo/logs/worker-latency.log

После завершения:
TMUX="" tmux send-keys -t "claude:4" "W-LATENCY COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:4" Enter
