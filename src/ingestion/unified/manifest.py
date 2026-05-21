***REMOVED*** src/ingestion/unified/manifest.py
"""Manifest-based file identity with copy-vs-rename detection.

Identity strategy (Option B — copy detection, fixes ***REMOVED***1603):

  A file_id is tied to *both* content_hash and original path.  When the same
  content_hash appears at a new path we decide whether it is a rename/move or
  a copy by checking whether the original path is still active:

  - **Rename/move** (original path no longer active): reuse the original
    file_id so downstream Qdrant records are not orphaned.
  - **Copy** (original path still active): the new path is a distinct source
    record and must receive its own file_id.

Before this fix the manifest only checked ``hash_to_id[content_hash]``,
meaning every second file with identical bytes silently collapsed to the same
file_id regardless of whether the first path was still active (***REMOVED***1603).

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
    """Manages stable file identity with copy-vs-rename detection (***REMOVED***1603).

    Identity strategy (in priority order):
    1. Exact composite key ``path:content_hash`` — same file, same content.
       Returns the existing file_id immediately.
    2. Content-hash seen before AND original path is **no longer active**
       (``path_to_hash`` does not contain the original path) — this is a
       rename/move.  Reuses the original file_id for downstream stability.
    3. Content-hash seen before BUT original path is **still active** — this
       is a copy.  Generates a fresh file_id so both source records remain
       distinct.  Prevents copy-collapse (***REMOVED***1603).
    4. Genuinely new file — generate fresh UUID.

    Stores three mappings:
    - key_to_id: ``path:content_hash`` → file_id (includes copy entries)
    - hash_to_id: content_hash → file_id  (first-seen / rename-stable anchor)
    - path_to_hash: relative_path → content_hash (tracks currently active paths)
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

            ***REMOVED*** Migrate: backfill hash_to_id from legacy key_to_id entries.
            if not self._hash_to_id and self._key_to_id:
                for composite_key, file_id in self._key_to_id.items():
                    ***REMOVED*** composite_key = "path:content_hash"
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

        Copy-vs-rename detection (Option B, fixes ***REMOVED***1603):
        - If the same content_hash was seen before at a path that is *no
          longer active* in ``_path_to_hash``, this is a rename/move → reuse
          the original file_id.
        - If the same content_hash was seen before at a path that is *still
          active*, this is a copy → generate a new file_id so both source
          records remain distinct.
        """
        composite_key = f"{path}:{content_hash}"
        with self._lock:
            ***REMOVED*** 1. Exact match: same path + same content (most common / idempotent)
            if composite_key in self._key_to_id:
                file_id = self._key_to_id[composite_key]

            elif content_hash in self._hash_to_id:
                ***REMOVED*** Hash was seen before — determine rename vs copy.
                ***REMOVED*** Find which paths currently hold this hash.
                active_paths_for_hash = {
                    p for p, h in self._path_to_hash.items() if h == content_hash
                }
                if not active_paths_for_hash:
                    ***REMOVED*** 2. Rename/move: original path no longer active → reuse id.
                    file_id = self._hash_to_id[content_hash]
                    self._key_to_id[composite_key] = file_id
                    logger.info(
                        "Manifest: reused file_id=%s for renamed path=%s (content_hash=%s)",
                        file_id,
                        path,
                        content_hash,
                    )
                else:
                    ***REMOVED*** 3. Copy: at least one path with this hash is still active
                    ***REMOVED***    → generate a distinct file_id to prevent copy-collapse (***REMOVED***1603).
                    file_id = uuid.uuid4().hex[:16]
                    self._key_to_id[composite_key] = file_id
                    logger.info(
                        "Manifest: new copy file_id=%s for path=%s "
                        "(content_hash=%s, original paths still active: %s)",
                        file_id,
                        path,
                        content_hash,
                        active_paths_for_hash,
                    )

            else:
                ***REMOVED*** 4. Genuinely new file
                file_id = uuid.uuid4().hex[:16]
                self._key_to_id[composite_key] = file_id
                self._hash_to_id[content_hash] = file_id
                logger.info("Manifest: new file_id=%s for path=%s", file_id, path)

            ***REMOVED*** Always update reverse mappings
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
