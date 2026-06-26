"""Local BGE-M3 embedding provider using FlagEmbedding package."""

import asyncio
import logging
import os
from collections.abc import Sequence
from typing import Any

from src.adapters.embeddings.base import EmbeddingProvider


logger = logging.getLogger(__name__)

# Singleton instances at the module level
_MODEL_INSTANCE: Any = None
_MODEL_INIT_LOCK = asyncio.Lock()  # Guards initialization of model
_INFERENCE_SEMAPHORE: asyncio.Semaphore | None = None


class LocalBgeM3Provider(EmbeddingProvider):
    """Local BGE-M3 embedding provider using FlagEmbedding package."""

    def __init__(
        self,
        model_name: str | None = None,
        use_fp16: bool | None = None,
        batch_size: int | None = None,
        max_length: int | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv("BGE_M3_MODEL", "BAAI/bge-m3")

        # Parse boolean env
        env_use_fp16 = os.getenv("BGE_M3_USE_FP16", "true").lower() in ("true", "1", "yes")
        self.use_fp16 = use_fp16 if use_fp16 is not None else env_use_fp16

        # Parse integers
        try:
            self.batch_size = batch_size or int(os.getenv("BGE_M3_BATCH_SIZE", "8"))
        except ValueError:
            self.batch_size = 8

        try:
            self.max_length = max_length or int(os.getenv("BGE_M3_MAX_LENGTH", "2048"))
        except ValueError:
            self.max_length = 2048

        try:
            self.max_concurrency = max_concurrency or int(os.getenv("BGE_M3_MAX_CONCURRENCY", "1"))
        except ValueError:
            self.max_concurrency = 1

    async def _get_model(self) -> Any:
        """Lazily load and return the FlagEmbedding model instance (singleton)."""
        global _MODEL_INSTANCE
        if _MODEL_INSTANCE is not None:
            return _MODEL_INSTANCE

        async with _MODEL_INIT_LOCK:
            # Re-check after acquiring lock
            if _MODEL_INSTANCE is not None:
                return _MODEL_INSTANCE

            try:
                # Lazy import inside _get_model() so module import does not trigger it
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as exc:
                raise ImportError(
                    "Local embedding dependencies are missing. Please install the 'ml-local' extra: "
                    "uv sync --extra ml-local (which installs FlagEmbedding)."
                ) from exc

            # Configure thread counts and options as required by env settings
            # TOKENIZERS_PARALLELISM=false, OMP_NUM_THREADS=2, MKL_NUM_THREADS=2, OPENBLAS_NUM_THREADS=2
            for thread_env in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"]:
                if thread_env not in os.environ:
                    os.environ[thread_env] = "2"
            if "TOKENIZERS_PARALLELISM" not in os.environ:
                os.environ["TOKENIZERS_PARALLELISM"] = "false"

            logger.info("Initializing local BGE-M3 model (singleton): %s", self.model_name)

            # asyncio.to_thread copies the current contextvars into the worker
            # thread (OTEL span context), unlike a bare
            # loop.run_in_executor(None, ...). See observability contextvars
            # contract.
            _MODEL_INSTANCE = await asyncio.to_thread(
                BGEM3FlagModel,
                self.model_name,
                use_fp16=self.use_fp16,
            )
            logger.info("Local BGE-M3 model initialized successfully.")
            return _MODEL_INSTANCE

    def _get_semaphore(self) -> asyncio.Semaphore:
        global _INFERENCE_SEMAPHORE
        if _INFERENCE_SEMAPHORE is None:
            _INFERENCE_SEMAPHORE = asyncio.Semaphore(self.max_concurrency)
        return _INFERENCE_SEMAPHORE

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute dense embeddings using FlagEmbedding."""
        if not texts:
            return []

        # Empty check / lazy load
        model = await self._get_model()
        sem = self._get_semaphore()

        async with sem:
            # Encode returns dict with 'dense_vecs', 'lexical_weights', etc.
            # asyncio.to_thread propagates contextvars to the worker thread
            # (observability contextvars contract).
            result = await asyncio.to_thread(
                model.encode,
                list(texts),
                batch_size=self.batch_size,
                max_length=self.max_length,
            )
            dense_vecs = result["dense_vecs"]
            # Convert list/numpy arrays to list of float lists.
            return [vec.tolist() if hasattr(vec, "tolist") else list(vec) for vec in dense_vecs]
