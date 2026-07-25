"""Local cache of catalog responses (`~/.cache/fairypcbot/`, spec section 6.3/10.7).

Also stores the sha256 of the original raw bytes (as received from the server, before any JSON
round-trip) — necessary because `json.dumps` does not reproduce the original response byte-for-byte
(key order, spacing), so the hash has to be computed once, at fetch time, and persisted alongside it
(see the documentation: provenance uses the sha256 of the raw bytes, never recomputed from a reserialization).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "fairypcbot"


@dataclass
class CachedResponse:
    data: dict
    sha256: str


def _cache_key(lcsc_id: str) -> str:
    return lcsc_id.replace(":", "_").replace("/", "_")


def cache_path(lcsc_id: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    return cache_dir / "easyeda" / f"{_cache_key(lcsc_id)}.json"


def read_cache(lcsc_id: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> CachedResponse | None:
    path = cache_path(lcsc_id, cache_dir)
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or "data" not in envelope or "sha256" not in envelope:
            return None
        return CachedResponse(data=envelope["data"], sha256=envelope["sha256"])
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(lcsc_id: str, data: dict, sha256: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    path = cache_path(lcsc_id, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {"sha256": sha256, "data": data}
    path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
