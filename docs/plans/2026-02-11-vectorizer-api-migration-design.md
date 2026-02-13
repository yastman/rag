# Vectorizer API Migration Design

**Issue:** test_vectorizers.py collection error + redisvl 0.14.0 API signature drift
**GitHub Issue:** https://github.com/yastman/rag/issues/155
**Date:** 2026-02-11
**Branch:** from current (154-feat-memory)

## Review notes (audit)

1. `redisvl==0.14.0` confirmed locally; `BaseVectorizer` public API now routes through
   `embed(content=..., text=...)` / `aembed(content=..., text=...)` and delegates to internal
   `_embed` / `_aembed`.
2. Existing `UserBaseVectorizer.embed(text: str, ...)` and `BgeM3CacheVectorizer.embed(text: str, ...)`
   are incompatible with keyword call `embed(content="...")` (`TypeError`).
3. `pytest.importorskip("redisvl")` does **not** catch all import-time exceptions; it handles
   `ImportError` family only. For broken optional env imports, keep explicit broad guard.

## Problem

### 1. Test collection crash (Medium)

`tests/unit/test_vectorizers.py` guard:

```python
try:
    import redisvl
except (ImportError, ModuleNotFoundError, ValueError):
    pytest.skip("redisvl not installed", allow_module_level=True)
```

Catches only 3 exception types. In incomplete envs (worktree without `uv sync`), redisvl
import can raise `RuntimeError`, `AttributeError`, `OSError` → collection error (exit code 2).

### 2. API signature drift (High — production bug)

redisvl 0.14.0 `BaseVectorizer.embed()` signature changed:

```python
# OLD (what our code overrides)
def embed(self, text: str, preprocess=None, as_buffer=False, **kwargs) -> list[float]

# NEW (redisvl 0.14.0 BaseVectorizer)
def embed(self, content=None, text=None, preprocess=None, as_buffer=False, skip_cache=False, **kwargs)
```

**Proven bug:** current overrides reject new keyword-style API:
- `UserBaseVectorizer().embed(content="test")` → `TypeError`
- `BgeM3CacheVectorizer().embed(content="test")` → `TypeError`

`SemanticCache._vectorize_prompt()` currently calls positional `embed(prompt)`, поэтому path еще
работает. Но новый keyword-style API уже сломан.

### 3. Architecture: override pattern wrong

redisvl 0.14.0 refactored `BaseVectorizer`:
- Public methods (`embed`, `embed_many`, `aembed`, `aembed_many`) — wrappers with caching, preprocessing, deprecated-arg handling
- Internal methods (`_embed`, `_embed_many`, `_aembed`, `_aembed_many`) — actual implementation

Our vectorizers override **public** methods, bypassing all base class features.

## Solution: Override internal methods (`_embed` / `_aembed`)

### Approach

1. Replace `embed()` override with `_embed(...)` — base class handles public API wrappers
2. Replace `aembed()` override with `_aembed(...)`
3. Same for `_embed_many` / `_aembed_many`
4. Keep `aclose()` (custom method, not in base class)

### Why NOT CustomVectorizer

`CustomVectorizer.__init__` runs `embed("dimension test")` at creation time — calls actual HTTP
service. Won't work without running containers. Subclassing `BaseVectorizer` + internal methods is
the correct pattern for network-backed vectorizers.

## Changes

### File 1: `telegram_bot/services/vectorizers.py`

#### UserBaseVectorizer

```python
class UserBaseVectorizer(BaseVectorizer):
    model: str = "deepvk/USER2-base"
    dims: int = 768
    base_url: str = "http://localhost:8003"
    timeout: float = 5.0
    model_config = {"arbitrary_types_allowed": True}

    _sync_client: httpx.Client | None = None
    _async_client: httpx.AsyncClient | None = None

    def __init__(self, base_url: str = "http://localhost:8003", **kwargs: Any):
        super().__init__(base_url=base_url, **kwargs)

    # --- HTTP client management (unchanged) ---
    def _get_sync_client(self) -> httpx.Client: ...
    async def _get_async_client(self) -> httpx.AsyncClient: ...

    # --- Internal methods (NEW — replace public overrides) ---
    def _embed(self, content: Any = "", text: Any = "", **kwargs: Any) -> list[float]:
        value = str(content or text)
        client = self._get_sync_client()
        response = client.post("/embed", json={"text": value})
        response.raise_for_status()
        return cast(list[float], response.json()["embedding"])

    def _embed_many(
        self,
        contents: list[Any] | None = None,
        texts: list[Any] | None = None,
        batch_size: int = 10,
        **kwargs: Any,
    ) -> list[list[float]]:
        values = [str(c) for c in (contents or texts or [])]
        client = self._get_sync_client()
        response = client.post("/embed_batch", json={"texts": values})
        response.raise_for_status()
        return cast(list[list[float]], response.json()["embeddings"])

    async def _aembed(self, content: Any = "", text: Any = "", **kwargs: Any) -> list[float]:
        value = str(content or text)
        client = await self._get_async_client()
        response = await client.post("/embed", json={"text": value})
        response.raise_for_status()
        return cast(list[float], response.json()["embedding"])

    async def _aembed_many(
        self,
        contents: list[Any] | None = None,
        texts: list[Any] | None = None,
        batch_size: int = 10,
        **kwargs: Any,
    ) -> list[list[float]]:
        values = [str(c) for c in (contents or texts or [])]
        client = await self._get_async_client()
        response = await client.post("/embed_batch", json={"texts": values})
        response.raise_for_status()
        return cast(list[list[float]], response.json()["embeddings"])

    async def aclose(self): ...  # unchanged
```

**Ключевые изменения:**
- `embed()` → `_embed(content/text)` — поддерживаем оба alias на internal уровне
- `str(content or text)` — защита от non-string input (base class может передать любой тип)
- Удалены `preprocess`, `as_buffer` параметры — ими управляет base class

#### BgeM3CacheVectorizer

```python
class BgeM3CacheVectorizer(BaseVectorizer):
    model: str = "BAAI/bge-m3"
    dims: int = 1024
    base_url: str = "http://bge-m3:8000"
    timeout: float = 30.0
    model_config = {"arbitrary_types_allowed": True}
    _async_client: httpx.AsyncClient | None = None

    def __init__(self, base_url: str = "http://bge-m3:8000", **kwargs: Any):
        super().__init__(base_url=base_url, **kwargs)

    def _embed(self, content: Any = "", text: Any = "", **kwargs: Any) -> list[float]:
        raise NotImplementedError("BgeM3CacheVectorizer: use vector= parameter")

    def _embed_many(
        self,
        contents: list[Any] | None = None,
        texts: list[Any] | None = None,
        batch_size: int = 10,
        **kwargs: Any,
    ) -> list[list[float]]:
        raise NotImplementedError("BgeM3CacheVectorizer: use vector= parameter")

    async def _aembed(self, content: Any = "", text: Any = "", **kwargs: Any) -> list[float]:
        value = str(content or text)
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        response = await self._async_client.post("/encode/dense", json={"texts": [value]})
        response.raise_for_status()
        data = response.json()
        vecs = data.get("dense_vecs") or data.get("embeddings")
        return cast(list[float], vecs[0])

    async def _aembed_many(
        self,
        contents: list[Any] | None = None,
        texts: list[Any] | None = None,
        batch_size: int = 10,
        **kwargs: Any,
    ) -> list[list[float]]:
        values = [str(c) for c in (contents or texts or [])]
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        response = await self._async_client.post("/encode/dense", json={"texts": values})
        response.raise_for_status()
        data = response.json()
        return cast(list[list[float]], data.get("dense_vecs") or data.get("embeddings"))
```

### File 2: `tests/unit/test_vectorizers.py`

#### Guard fix

```python
# OLD
try:
    import redisvl
except (ImportError, ModuleNotFoundError, ValueError):
    pytest.skip("redisvl not installed", allow_module_level=True)

# NEW — catches optional-dependency import failures in partially provisioned envs
try:
    import redisvl  # noqa: F401
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(
        f"redisvl unavailable/broken import: {type(exc).__name__}: {exc}",
        allow_module_level=True,
    )
```

#### Test updates

Тесты мокают `_sync_client` / `_async_client` напрямую — это не меняется.
Но вызов через public API теперь нужно явно проверить в трех формах:
- `embed("тест")` (позиционный)
- `embed(content="тест")` (новый API)
- `embed(text="тест")` (deprecated alias, все еще поддерживается base class)

**Два варианта тестирования:**

**A) Тестировать internal `_embed`/`_aembed` напрямую (рекомендуется):**

```python
async def test_aembed_single_text(self):
    vectorizer = UserBaseVectorizer()
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": [0.1] * 768}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    vectorizer._async_client = mock_client

    # Тестируем internal method напрямую
    result = await vectorizer._aembed("тестовый запрос")
    assert len(result) == 768
    mock_client.post.assert_called_once_with("/embed", json={"text": "тестовый запрос"})
```

**B) Тестировать через public API (проверяет интеграцию с base class):**

```python
def test_embed_via_public_api(self):
    vectorizer = UserBaseVectorizer()
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": [0.1] * 768}
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    vectorizer._sync_client = mock_client

    # Через public API — как вызывает SemanticCache
    result = vectorizer.embed(content="тест")
    assert result == [0.1] * 768
```

**Рекомендация:** вариант A для unit-тестов (тестируем нашу логику), + 1-2 теста варианта B
(проверяем совместимость с base class API).

**Обязательные compatibility-тесты (добавить):**
- `UserBaseVectorizer.embed(content="...")` больше не падает `TypeError`
- `UserBaseVectorizer.aembed(content="...")` больше не падает `TypeError`
- `BgeM3CacheVectorizer.embed(content="...")` теперь дает `NotImplementedError` (а не `TypeError`)
- `UserBaseVectorizer.embed(text="...")` продолжает работать через deprecated alias

### File 3: `tests/integration/test_userbase_cache.py`

`aembed(query)` → base class → `_aembed(content=query)`. Вызов позиционный, работает без изменений.

## Checklist

- [ ] Migrate `UserBaseVectorizer`: public → internal methods
- [ ] Migrate `BgeM3CacheVectorizer`: public → internal methods
- [ ] Fix test guard: broad skip on optional `redisvl` import failure
- [ ] Update unit tests: mock + assert internal methods
- [ ] Add 1-2 public API compatibility tests
- [ ] Verify compatibility: positional / `content=` / `text=` calls
- [ ] Run `make check` (ruff + mypy)
- [ ] Run `uv run pytest tests/unit/test_vectorizers.py -v`
- [ ] Verify no `TypeError` for `embed(content=...)` and `aembed(content=...)`
