from __future__ import annotations

import json
from pathlib import Path

from fairypcbot.catalog.easyeda import EasyedaResolver

PAD_LINE = "PAD~RECT~0~0~5~3~1~~1~0~~0~gge1~0~"

RESPONSE_WITH_PACKAGE_DETAIL = {
    "result": {
        "title": "TJA1051T/3",
        "dataStr": {"head": {"c_para": {"Manufacturer": "NXP", "package": "SOIC-8"}}},
        "packageDetail": {"dataStr": {"shape": [PAD_LINE]}},
    }
}

RESPONSE_WITHOUT_FOOTPRINT = {
    "result": {
        "title": "R0402",
        "dataStr": {"head": {"c_para": {"package": "R0402"}}},
    }
}


def _fake_http_get(payload: dict):
    def _get(url: str, timeout: float) -> bytes:
        return json.dumps(payload).encode("utf-8")

    return _get


def test_fetch_stub_attaches_footprint_when_present(tmp_path: Path):
    resolver = EasyedaResolver(
        cache_dir=tmp_path, http_get=_fake_http_get(RESPONSE_WITH_PACKAGE_DETAIL), use_cache=False
    )
    part = resolver.fetch_stub("lcsc:C81036")
    assert part.footprint is not None
    assert len(part.footprint.pads) == 1
    assert part.provenance["footprint"].source == "easyeda_api"


def test_fetch_stub_footprint_missing_when_absent(tmp_path: Path):
    resolver = EasyedaResolver(
        cache_dir=tmp_path, http_get=_fake_http_get(RESPONSE_WITHOUT_FOOTPRINT), use_cache=False
    )
    part = resolver.fetch_stub("lcsc:C1")
    assert part.footprint is None
    assert part.provenance["footprint"].source == "missing"
