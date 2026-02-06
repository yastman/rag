# src/ingestion/unified/manifest.py
"""Manifest-based file identity for rename/move detection.

Maps content_hash → stable file_id (UUID) so that when a file is
renamed or moved, it keeps its identity in Qdrant instead of creating
duplicates.

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
    """Manages stable file identity based on content hashes.

    Stores two mappings:
    - hash_to_id: content_hash → stable file_id (never changes for same content)
    - path_to_hash: relative_path → content_hash (tracks current locations)
    """

    def __init__(self, manifest_dir: Path) -> None:
        self._path = manifest_dir / ".gdrive_manifest.json"
        self._lock = threading.Lock()
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
            self._hash_to_id = data.get("hash_to_id", {})
            self._path_to_hash = data.get("path_to_hash", {})
            logger.info(
                "Loaded manifest: %d content entries, %d path entries",
                len(self._hash_to_id),
                len(self._path_to_hash),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load manifest %s: %s — starting fresh", self._path, e)
            self._hash_to_id = {}
            self._path_to_hash = {}

    def save(self) -> None:
        """Persist manifest to disk. Must be called with lock held."""
        data = {
            "hash_to_id": self._hash_to_id,
            "path_to_hash": self._path_to_hash,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)

    def get_or_create_id(self, path: str, content_hash: str) -> str:
        """Return a stable file_id for the given path and content hash.

        If the content_hash already has a stable ID (from this or any other
        path), reuse it.  Otherwise generate a new one.  The path mapping
        is always updated.
        """
        with self._lock:
            if content_hash in self._hash_to_id:
                file_id = self._hash_to_id[content_hash]
                old_hash = self._path_to_hash.get(path)
                if old_hash != content_hash:
                    logger.info(
                        "Manifest: path=%s → reusing file_id=%s (content match)", path, file_id
                    )
            else:
                file_id = uuid.uuid4().hex[:16]
                self._hash_to_id[content_hash] = file_id
                logger.info("Manifest: new file_id=%s for path=%s", file_id, path)

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
