from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fairypcbot.catalog.easyeda import EasyedaResolver

FAKE_RESPONSE = {
    "result": {
        "title": "TJA1051T/3",
        "dataStr": {"head": {"c_para": {"Manufacturer": "NXP", "package": "SOIC-8"}}},
    }
}


def _fake_http_get(payload: dict):
    def _get(url: str, timeout: float) -> bytes:
        return json.dumps(payload).encode("utf-8")

    return _get


def test_fetch_stub_provenance_has_sha256_of_raw_bytes(tmp_path: Path):
    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=_fake_http_get(FAKE_RESPONSE), use_cache=False)
    part = resolver.fetch_stub("lcsc:C81036")
    expected = hashlib.sha256(json.dumps(FAKE_RESPONSE).encode("utf-8")).hexdigest()
    assert part.provenance["mpn"].sha256 == expected


def test_cache_roundtrip_preserves_original_hash(tmp_path: Path):
    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=_fake_http_get(FAKE_RESPONSE), use_cache=True)
    _, digest1 = resolver.fetch_raw_with_hash("lcsc:C81036")

    # segunda chamada vem do cache — o hash deve ser o mesmo, não recalculado sobre uma reserialização
    _, digest2 = resolver.fetch_raw_with_hash("lcsc:C81036")
    assert digest1 == digest2
    assert digest1 == hashlib.sha256(json.dumps(FAKE_RESPONSE).encode("utf-8")).hexdigest()


def test_fetch_stub_with_hash_returns_same_digest_as_fetch_raw(tmp_path: Path):
    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=_fake_http_get(FAKE_RESPONSE), use_cache=False)
    part, digest = resolver.fetch_stub_with_hash("lcsc:C1")
    assert part.provenance["mpn"].sha256 == digest
