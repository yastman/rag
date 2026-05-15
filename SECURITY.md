# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please report it responsibly.

- **Do not open public issues or pull requests** for security-sensitive findings.
- **Do not include secrets, tokens, private data, CRM data, phone numbers, or exploit details** in any public communication.
- If GitHub Security Advisories are enabled for this repository, prefer opening a private advisory.
- Otherwise, open a minimal public issue requesting security contact without including sensitive details, and a maintainer will reach out privately.

## Secrets and Credentials

- Do **not** commit secrets, API keys, passwords, tokens, or other credentials to this repository.
- If you accidentally commit sensitive material, notify the maintainers immediately so it can be rotated and removed from history.
- Use `.env.example` as the public contract for required environment variables.
- Treat Telegram, Kommo, Langfuse, LiveKit, and cloud credentials as external secrets, not repository content.
