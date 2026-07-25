from __future__ import annotations

import json
from pathlib import Path

import pytest

from fairypcbot.catalog.base import CatalogFetchError
from fairypcbot.catalog.easyeda import EasyedaResolver

FAKE_RESPONSE = {
    "success": True,
    "result": {
        "title": "TJA1051T/3",
        "dataStr": {"head": {"c_para": {"Manufacturer": "NXP", "package": "SOIC-8"}}},
    },
}


def _fake_http_get(payload: dict):
    def _get(url: str, timeout: float) -> bytes:
        return json.dumps(payload).encode("utf-8")

    return _get


def test_fetch_stub_extracts_available_fields(tmp_path: Path):
    resolver = EasyedaResolver(
        cache_dir=tmp_path, http_get=_fake_http_get(FAKE_RESPONSE), use_cache=False
    )
    part = resolver.fetch_stub("lcsc:C81036")
    assert part.mpn == "TJA1051T/3"
    assert part.manufacturer == "NXP"
    assert part.package.name == "SOIC-8"
    assert part.class_ is None  # never invented
    assert part.provenance["mpn"].source == "easyeda_api"
    assert part.provenance["class"].source == "missing"


def test_fetch_stub_missing_fields_marked_as_missing(tmp_path: Path):
    resolver = EasyedaResolver(
        cache_dir=tmp_path, http_get=_fake_http_get({"result": {}}), use_cache=False
    )
    part = resolver.fetch_stub("lcsc:C1")
    assert part.mpn == "UNKNOWN"
    assert part.provenance["mpn"].source == "missing"


def test_fetch_stub_captures_3d_model_from_footprint_head(tmp_path: Path):
    """uuid_3d lives in packageDetail.dataStr.head, not in the symbol doc head — actual finding
    when inspecting a cached response (see the documentation)."""
    payload = {
        "success": True,
        "result": {
            "title": "1N4148",
            "dataStr": {"head": {"c_para": {"Manufacturer": "Diotec", "package": "DO-35"}}},
            "packageDetail": {
                "dataStr": {
                    "head": {"uuid_3d": "bd8a21c2800f4128bac447937d6ec109", "c_para": {"3DModel": "DO-35_BD1.7"}}
                }
            },
        },
    }
    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=_fake_http_get(payload), use_cache=False)
    part = resolver.fetch_stub("lcsc:C22434654")
    assert part.model_3d is not None
    assert part.model_3d.uuid == "bd8a21c2800f4128bac447937d6ec109"
    assert part.model_3d.name == "DO-35_BD1.7"
    assert part.provenance["model_3d"].source == "easyeda_api"


def test_fetch_stub_captures_symbol_from_same_dataStr(tmp_path: Path):
    """Real symbol comes from the SAME dataStr.shape already used for manufacturer/package (no extra
    API call) — see the documentation."""
    payload = {
        "success": True,
        "result": {
            "title": "1N4148",
            "dataStr": {
                "head": {"c_para": {"Manufacturer": "Diotec", "package": "DO-35"}},
                "shape": [
                    "P~show~0~2~420~300~0~gge11~0^^420~300^^M 420 300 h -10~#880000^^0~407~303~0~A~end~~~#0000FF^^0~413~299~0~2~start~~~#0000FF^^0~413~300^^0~M 410 297 L 407 300 L 410 303",
                    "P~show~0~1~380~300~180~gge20~0^^380~300^^M 380 300 h 10~#880000^^0~393~303~0~C~start~~~#0000FF^^0~387~299~0~1~end~~~#0000FF^^0~387~300^^0~M 390 303 L 393 300 L 390 297",
                ],
            },
        },
    }
    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=_fake_http_get(payload), use_cache=False)
    part = resolver.fetch_stub("lcsc:C22434654")
    assert part.symbol is not None
    assert len(part.symbol.pins) == 2
    assert part.provenance["symbol"].source == "easyeda_api"


def test_fetch_stub_without_pin_shapes_has_no_symbol(tmp_path: Path):
    resolver = EasyedaResolver(
        cache_dir=tmp_path, http_get=_fake_http_get(FAKE_RESPONSE), use_cache=False
    )
    part = resolver.fetch_stub("lcsc:C81036")
    assert part.symbol is None
    assert part.provenance["symbol"].source == "missing"


def test_fetch_stub_without_package_detail_has_no_3d_model(tmp_path: Path):
    resolver = EasyedaResolver(
        cache_dir=tmp_path, http_get=_fake_http_get(FAKE_RESPONSE), use_cache=False
    )
    part = resolver.fetch_stub("lcsc:C81036")
    assert part.model_3d is None
    assert part.provenance["model_3d"].source == "missing"


def test_fetch_raw_uses_cache_on_second_call(tmp_path: Path):
    calls = {"n": 0}

    def counting_get(url: str, timeout: float) -> bytes:
        calls["n"] += 1
        return json.dumps(FAKE_RESPONSE).encode("utf-8")

    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=counting_get, use_cache=True)
    resolver.fetch_raw("lcsc:C81036")
    resolver.fetch_raw("lcsc:C81036")
    assert calls["n"] == 1


def test_network_failure_raises_catalog_fetch_error(tmp_path: Path):
    def failing_get(url: str, timeout: float) -> bytes:
        raise OSError("network unreachable")

    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=failing_get, use_cache=False)
    with pytest.raises(CatalogFetchError):
        resolver.fetch_stub("lcsc:C1")


def test_non_json_response_raises_catalog_fetch_error(tmp_path: Path):
    def bad_get(url: str, timeout: float) -> bytes:
        return b"<html>not json</html>"

    resolver = EasyedaResolver(cache_dir=tmp_path, http_get=bad_get, use_cache=False)
    with pytest.raises(CatalogFetchError):
        resolver.fetch_stub("lcsc:C1")
