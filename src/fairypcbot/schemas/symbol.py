"""Schematic symbol geometry (actual pins) — see the documentation.

Populated by `catalog fetch` from the actual EasyEDA symbol document (`dataStr` from the API
response — the same request already used for footprint, no extra call). Mirrors the pattern of
`schemas/footprint.py`: hand-written descriptors keep working without this (a missing symbol is
an explicit degradation in the emitter, never an invented glyph)."""

from __future__ import annotations

from fairypcbot.schemas.base import FairyBaseModel


class SymbolPin(FairyBaseModel):
    number: str
    name: str
    x_mm: float
    y_mm: float
    length_mm: float
    rotation_deg: float = 0.0
    # Flag/orientation of the pin name LABEL, extracted from the API data itself (not invented
    # — see `catalog/easyeda_symbol.py::_PIN_NAME_RE`). `name_hidden=True` reproduces an actual
    # symbol where the author hid the name (common on pins where the number alone suffices,
    # e.g. numbered buses); default `False` (name visible) covers symbols without this data
    # (safe degradation).
    name_hidden: bool = False
    name_rotation_deg: float = 0.0


class SymbolPolyline(FairyBaseModel):
    points_mm: list[tuple[float, float]]
    closed: bool = False


class Symbol(FairyBaseModel):
    pins: list[SymbolPin] = []
    polylines: list[SymbolPolyline] = []
