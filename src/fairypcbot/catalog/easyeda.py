"""EasyEDA resolver (spec section 7): LCSC part number -> ComponentPart stub.

Uses the same public endpoint reverse-engineered by the easyeda2kicad project (an engineering
reference, not a conceptual dependency — the fairypcbot IR has no knowledge of EasyEDA outside
this module and `emit/easyeda_std.py`). Implemented with the stdlib `urllib` to avoid adding a new
HTTP dependency (spec section 10.6: minimal dependencies).

Never invents data: fields that do not come from the API are left missing, marked with
`Provenance(source="missing")`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fairypcbot.audit.hashing import sha256_bytes
from fairypcbot.catalog.base import CatalogFetchError
from fairypcbot.catalog.cache import DEFAULT_CACHE_DIR, read_cache, write_cache
from fairypcbot.catalog.easyeda_footprint import parse_easyeda_footprint_shapes
from fairypcbot.catalog.easyeda_symbol import parse_easyeda_symbol_shapes
from fairypcbot.schemas.component_part import ComponentPart, Model3D, PackageSpec
from fairypcbot.schemas.footprint import Footprint
from fairypcbot.schemas.provenance import Provenance
from fairypcbot.schemas.symbol import Symbol

EASYEDA_API_URL_TEMPLATE = "https://easyeda.com/api/products/{lcsc_id}/components?version=6.4.19"

HttpGet = Callable[[str, float], bytes]


def _default_http_get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fairypcbot/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class EasyedaResolver:
    def __init__(
        self,
        timeout: float = 10.0,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        http_get: HttpGet = _default_http_get,
        use_cache: bool = True,
    ) -> None:
        self.timeout = timeout
        self.cache_dir = cache_dir
        self.http_get = http_get
        self.use_cache = use_cache

    def _short_id(self, lcsc_id: str) -> str:
        return lcsc_id.split(":", 1)[1] if ":" in lcsc_id else lcsc_id

    def fetch_raw(self, lcsc_id: str) -> dict[str, Any]:
        return self.fetch_raw_with_hash(lcsc_id)[0]

    def fetch_raw_with_hash(self, lcsc_id: str) -> tuple[dict[str, Any], str]:
        """Returns (data, sha256) — the hash is always of the raw HTTP response bytes as
        received, never a reserialization (see the docstring of `catalog/cache.py`)."""
        if self.use_cache:
            cached = read_cache(lcsc_id, self.cache_dir)
            if cached is not None:
                return cached.data, cached.sha256

        url = EASYEDA_API_URL_TEMPLATE.format(lcsc_id=self._short_id(lcsc_id))
        try:
            raw_bytes = self.http_get(url, self.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CatalogFetchError(
                f"Could not contact the EasyEDA API for '{lcsc_id}': {exc}"
            ) from exc

        try:
            data = json.loads(raw_bytes)
        except json.JSONDecodeError as exc:
            raise CatalogFetchError(
                f"Unexpected (non-JSON) response from the EasyEDA API for '{lcsc_id}'"
            ) from exc

        digest = sha256_bytes(raw_bytes)
        if self.use_cache:
            write_cache(lcsc_id, data, digest, self.cache_dir)
        return data, digest

    def _extract_footprint_shape_lines(self, result: dict[str, Any]) -> list[str] | None:
        """Tries to locate the footprint shape list in the response.

        **Best-effort, not validated live** (see the documentation and the docstring of
        `catalog/easyeda_footprint.py`): tries the paths documented by easyeda2kicad, in the most
        likely order first. If nothing matches, returns None (degrades to "no geometry").
        """
        package_detail = result.get("packageDetail")
        if isinstance(package_detail, dict):
            shape = package_detail.get("dataStr", {}).get("shape")
            if isinstance(shape, list):
                return shape

        data_str = result.get("dataStr")
        if isinstance(data_str, dict):
            shape = data_str.get("shape")
            if isinstance(shape, list):
                return shape

        return None

    def fetch_stub(self, lcsc_id: str) -> ComponentPart:
        return self.fetch_stub_with_hash(lcsc_id)[0]

    def fetch_stub_with_hash(self, lcsc_id: str) -> tuple[ComponentPart, str]:
        """Like `fetch_stub`, but also returns the sha256 of the raw response bytes — used by
        the CLI to record `component_package` provenance (see `catalog/package_writer.py`)."""
        raw, digest = self.fetch_raw_with_hash(lcsc_id)
        result = raw.get("result") if isinstance(raw.get("result"), dict) else raw

        title = result.get("title") or result.get("name")
        attrs: dict[str, Any] = {}
        data_str = result.get("dataStr")
        if isinstance(data_str, dict):
            attrs = data_str.get("head", {}).get("c_para", {}) or {}
        manufacturer = attrs.get("Manufacturer") or attrs.get("manufacturer")
        package_name = attrs.get("package") or attrs.get("Package")

        footprint: Footprint | None = None
        shape_lines = self._extract_footprint_shape_lines(result)
        if shape_lines:
            parsed = parse_easyeda_footprint_shapes(shape_lines)
            if parsed.pads:
                footprint = parsed

        # Real symbol: same `result.dataStr.shape` from the symbol doc (docType 2) already used
        # above for manufacturer/package — not an extra API call (see the documentation).
        symbol: Symbol | None = None
        if isinstance(data_str, dict):
            symbol_shape = data_str.get("shape")
            if isinstance(symbol_shape, list):
                parsed_symbol = parse_easyeda_symbol_shapes(symbol_shape)
                if parsed_symbol.pins:
                    symbol = parsed_symbol

        # uuid_3d lives in the head of the FOOTPRINT doc (packageDetail.dataStr.head), not in the
        # head of the symbol doc (result.dataStr.head, used above for manufacturer/package) — they
        # are two different documents in the same API response (finding from inspecting a real
        # cached response, see the documentation).
        model_3d: Model3D | None = None
        package_detail = result.get("packageDetail")
        if isinstance(package_detail, dict):
            fp_head = (package_detail.get("dataStr") or {}).get("head") or {}
            uuid_3d = fp_head.get("uuid_3d")
            if uuid_3d:
                name_3d = (fp_head.get("c_para") or {}).get("3DModel")
                model_3d = Model3D(uuid=uuid_3d, name=name_3d)

        now = datetime.now(UTC)
        ref = EASYEDA_API_URL_TEMPLATE.format(lcsc_id=self._short_id(lcsc_id))
        from_api = Provenance(source="easyeda_api", ref=ref, timestamp=now, sha256=digest)
        missing = Provenance(source="missing", ref="", timestamp=now)

        part = ComponentPart(
            kind="component_part",
            id=lcsc_id,
            class_=None,
            mpn=title or "UNKNOWN",
            manufacturer=manufacturer or "UNKNOWN",
            package=PackageSpec(name=package_name or "UNKNOWN", source="easyeda"),
            pinout={},
            params={},
            datasheet_url=None,
            footprint=footprint,
            symbol=symbol,
            model_3d=model_3d,
            provenance={
                "mpn": from_api if title else missing,
                "manufacturer": from_api if manufacturer else missing,
                "package": from_api if package_name else missing,
                "footprint": from_api if footprint else missing,
                "symbol": from_api if symbol else missing,
                "model_3d": from_api if model_3d else missing,
                "class": missing,
                "pinout": missing,
                "datasheet_url": missing,
            },
        )
        return part, digest
