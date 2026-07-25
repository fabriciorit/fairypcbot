"""Common contract for catalog resolvers."""

from __future__ import annotations

from typing import Protocol

from fairypcbot.schemas.component_part import ComponentPart


class CatalogFetchError(Exception):
    """Failure contacting the external source (timeout, network unavailable, unexpected response)."""


class CatalogResolver(Protocol):
    def fetch_stub(self, lcsc_id: str) -> ComponentPart:
        """Returns a *stub* ComponentPart: never invents data — fields that were not obtained are
        left missing/empty with `missing` provenance (spec section 7)."""
        ...
