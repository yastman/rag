W-ENV: Скопируй Telegram env переменные с VPS

Работай из /repo

Шаги:

1. Подключись к VPS и прочитай env:
   ssh vps "cat /opt/rag-fresh/.env" > /tmp/vps-env.txt

2. Прочитай /tmp/vps-env.txt и найди все TELEGRAM_ переменные:
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_API_ID (если есть)
   - TELEGRAM_API_HASH (если есть)
   - TELEGRAM_ALERTING_BOT_TOKEN (если есть)
   - TELEGRAM_ALERTING_CHAT_ID (если есть)
   - Любые другие TELEGRAM_*

3. Прочитай локальный .env файл: /repo/.env

4. Обнови локальный .env — добавь или обнови TELEGRAM_ переменные из VPS
   Не удаляй другие переменные которые уже есть в локальном .env

5. Проверь что .env содержит все нужные TELEGRAM_ переменные

НЕ показывай токены в логах!

Логирование в /repo/logs/worker-env-copy.log (APPEND):
[START] timestamp
[DONE] timestamp — X env vars copied
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-ENV COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
