# src/ingestion/unified/manifest.py
"""Manifest-based file identity with rename/move stability.

Uses content_hash as the primary identity key so that a renamed or moved
file keeps its original file_id.  Falls back to the legacy composite key
``relative_path:content_hash`` for backward-compatibility with existing
manifests.

The manifest is persisted as `.gdrive_manifest.json` in the drive-sync
root directory.
"""

import hashlib
import json
import logging
import threading
import uuid
from pathlib import Path


logger = logging.getLogger(__name__)


class GDriveManifest:
    """Manages stable file identity with rename/move stability.

    Identity strategy (in priority order):
    1. Exact composite key ``path:content_hash`` — same file, same content.
    2. Content hash lookup ``hash_to_id[content_hash]`` — file renamed/moved
       but content unchanged.  Reuses the original file_id.
    3. New file — generate fresh UUID.

    Stores three mappings:
    - key_to_id: ``path:content_hash`` → file_id (legacy, kept for compat)
    - hash_to_id: content_hash → file_id (primary identity, rename-stable)
    - path_to_hash: relative_path → content_hash (tracks current locations)
    """

    def __init__(self, manifest_dir: Path) -> None:
        self._path = manifest_dir / ".gdrive_manifest.json"
        self._lock = threading.Lock()
        self._key_to_id: dict[str, str] = {}
        self._hash_to_id: dict[str, str] = {}
        self._path_to_hash: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        """Load manifest from disk."""
        if not self._path.exists():
            logger.info("No manifest found at %s, starting fresh", self._path)
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._key_to_id = data.get("key_to_id", {})
            self._hash_to_id = data.get("hash_to_id", {})
            self._path_to_hash = data.get("path_to_hash", {})

            # Migrate: backfill hash_to_id from legacy key_to_id entries.
            if not self._hash_to_id and self._key_to_id:
                for composite_key, file_id in self._key_to_id.items():
                    # composite_key = "path:content_hash"
                    parts = composite_key.rsplit(":", 1)
                    if len(parts) == 2:
                        content_hash = parts[1]
                        self._hash_to_id.setdefault(content_hash, file_id)
                logger.info(
                    "Migrated %d hash_to_id entries from legacy manifest",
                    len(self._hash_to_id),
                )

            logger.info(
                "Loaded manifest: %d identity entries, %d hash entries, %d path entries",
                len(self._key_to_id),
                len(self._hash_to_id),
                len(self._path_to_hash),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load manifest %s: %s — starting fresh", self._path, e)
            self._key_to_id = {}
            self._hash_to_id = {}
            self._path_to_hash = {}

    def save(self) -> None:
        """Persist manifest to disk. Must be called with lock held."""
        data = {
            "hash_to_id": self._hash_to_id,
            "key_to_id": self._key_to_id,
            "path_to_hash": self._path_to_hash,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)

    def get_or_create_id(self, path: str, content_hash: str) -> str:
        """Return a stable file_id for the given path and content hash.

        Rename/move stable: if content_hash was seen before (at any path),
        the original file_id is reused.
        """
        composite_key = f"{path}:{content_hash}"
        with self._lock:
            # 1. Exact match: same path + same content (most common)
            if composite_key in self._key_to_id:
                file_id = self._key_to_id[composite_key]
            # 2. Content seen before at different path (rename/move)
            elif content_hash in self._hash_to_id:
                file_id = self._hash_to_id[content_hash]
                self._key_to_id[composite_key] = file_id
                logger.info(
                    "Manifest: reused file_id=%s for renamed path=%s (content_hash=%s)",
                    file_id,
                    path,
                    content_hash,
                )
            # 3. Genuinely new file
            else:
                file_id = uuid.uuid4().hex[:16]
                self._key_to_id[composite_key] = file_id
                logger.info("Manifest: new file_id=%s for path=%s", file_id, path)

            # Always update reverse mappings
            self._hash_to_id[content_hash] = file_id
            self._path_to_hash[path] = content_hash
            self.save()
            return file_id

    def remove(self, path: str) -> None:
        """Remove a path entry. Keeps hash→id mapping for future reuse."""
        with self._lock:
            if path in self._path_to_hash:
                del self._path_to_hash[path]
                self.save()
                logger.debug("Manifest: removed path=%s", path)


def compute_content_hash_from_bytes(content: bytes) -> str:
    """Compute a short SHA-256 hash from raw file bytes."""
    return hashlib.sha256(content).hexdigest()[:16]
