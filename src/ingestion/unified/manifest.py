# src/ingestion/unified/manifest.py
"""Manifest-based file identity using (path, content_hash) composite key.

Maps ``relative_path:content_hash`` → stable file_id (UUID).
Two different files with identical content receive distinct IDs.

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
    """Manages stable file identity based on (path, content_hash) pairs.

    Stores two mappings:
    - key_to_id: ``path:content_hash`` → stable file_id (unique per file)
    - path_to_hash: relative_path → content_hash (tracks current locations)
    """

    def __init__(self, manifest_dir: Path) -> None:
        self._path = manifest_dir / ".gdrive_manifest.json"
        self._lock = threading.Lock()
        self._key_to_id: dict[str, str] = {}
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
            self._path_to_hash = data.get("path_to_hash", {})
            logger.info(
                "Loaded manifest: %d identity entries, %d path entries",
                len(self._key_to_id),
                len(self._path_to_hash),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load manifest %s: %s — starting fresh", self._path, e)
            self._key_to_id = {}
            self._path_to_hash = {}

    def save(self) -> None:
        """Persist manifest to disk. Must be called with lock held."""
        data = {
            "key_to_id": self._key_to_id,
            "path_to_hash": self._path_to_hash,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)

    def get_or_create_id(self, path: str, content_hash: str) -> str:
        """Return a stable file_id for the given path and content hash.

        Uses ``path:content_hash`` as composite key so that different files
        with identical content get distinct IDs.
        """
        composite_key = f"{path}:{content_hash}"
        with self._lock:
            if composite_key in self._key_to_id:
                file_id = self._key_to_id[composite_key]
            else:
                file_id = uuid.uuid4().hex[:16]
                self._key_to_id[composite_key] = file_id
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
