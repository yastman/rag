"""Local bot health check for native startup prerequisites."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import urlopen

import redis.asyncio as redis
from redis.exceptions import AuthenticationError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QDRANT_COLLECTION = "gdrive_documents_bge"


def _read_var_from_dotenv(name: str) -> str:
    dotenv_path = PROJECT_ROOT / ".env"
    if not dotenv_path.exists():
        return ""

    pattern = re.compile(
        rf"^[ \t]*(?:export[ \t]+)?{re.escape(name)}[ \t]*=[ \t]*['\"]?([^'\"#\n]+)"
    )
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return ""


def resolve_qdrant_collection() -> str:
    if os.getenv("QDRANT_COLLECTION"):
        return os.environ["QDRANT_COLLECTION"]

    dotenv_value = _read_var_from_dotenv("QDRANT_COLLECTION")
    if dotenv_value:
        return dotenv_value

    compose_text = (PROJECT_ROOT / "compose.yml").read_text(encoding="utf-8")
    match = re.search(r"QDRANT_COLLECTION:\s*\$\{QDRANT_COLLECTION:-([^}]+)\}", compose_text)
    if match:
        return match.group(1).strip()
    return DEFAULT_QDRANT_COLLECTION


def resolve_redis_urls() -> list[str]:
    base_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    if "@" in base_url:
        return [base_url]

    urls: list[str] = []
    dotenv_password = _read_var_from_dotenv("REDIS_PASSWORD")
    for password in (os.getenv("REDIS_PASSWORD", ""), dotenv_password, "dev_redis_pass"):
        if password:
            auth_url = base_url.replace("redis://", f"redis://:{password}@", 1)
            if auth_url not in urls:
                urls.append(auth_url)

    if base_url not in urls:
        urls.append(base_url)
    return urls


def _strip_trailing_slash(url: str) -> str:
    return url.removesuffix("/")


def _resolve_collection_to_check() -> str:
    base_collection = resolve_qdrant_collection()
    base_collection = base_collection.removesuffix("_binary")
    base_collection = base_collection.removesuffix("_scalar")

    quantization_mode = os.getenv("QDRANT_QUANTIZATION_MODE", "off")
    if quantization_mode == "scalar":
        return f"{base_collection}_scalar"
    if quantization_mode == "binary":
        return f"{base_collection}_binary"
    return base_collection


def check_qdrant() -> tuple[bool, str]:
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_to_check = _resolve_collection_to_check()
    try:
        with urlopen(f"{qdrant_url}/collections", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"Qdrant unreachable at {qdrant_url}: {exc}"

    names = [item["name"] for item in payload.get("result", {}).get("collections", [])]
    if collection_to_check not in names:
        mode = os.getenv("QDRANT_QUANTIZATION_MODE", "off")
        return False, f"Qdrant collection '{collection_to_check}' not found (mode={mode})"

    return True, f"Qdrant collection exists: {collection_to_check}"


async def check_redis() -> tuple[bool, str]:
    last_error: Exception | None = None
    for redis_url in resolve_redis_urls():
        client = redis.from_url(redis_url, decode_responses=True)
        try:
            await client.ping()
            return True, f"Redis OK: {redis_url}"
        except AuthenticationError as exc:
            last_error = exc
        except Exception as exc:  # pragma: no cover - environment dependent
            last_error = exc
        finally:
            await client.aclose()

    return False, f"Redis unreachable or auth failed: {last_error}"


def check_llm() -> tuple[bool, str]:
    llm_base_url = os.getenv("LLM_BASE_URL", os.getenv("LITELLM_BASE_URL", "http://localhost:4000"))
    normalized = _strip_trailing_slash(llm_base_url)
    health_base = normalized.removesuffix("/v1")
    health_url = f"{health_base}/health/liveliness"
    models_url = f"{normalized}/models"

    try:
        with urlopen(health_url, timeout=10):
            return True, f"LLM health OK: {health_url}"
    except Exception:
        try:
            with urlopen(models_url, timeout=10):
                return True, f"LLM models OK: {models_url}"
        except Exception as exc:  # pragma: no cover - environment dependent
            return False, f"LLM endpoint not responding at {llm_base_url}: {exc}"


async def main() -> int:
    checks = [
        ("Redis", await check_redis()),
        ("Qdrant", check_qdrant()),
        ("LLM", check_llm()),
    ]

    failures = False
    for label, (ok, message) in checks:
        prefix = "PASS" if ok else "FAIL"
        stream = sys.stdout if ok else sys.stderr
        print(f"{prefix}: {label} - {message}", file=stream)
        failures = failures or not ok

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
