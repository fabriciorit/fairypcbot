"""Registry of placement heuristics (`compact`, `spread`, `thermal_first` — M4, spec section 5.2)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_HEURISTICS: dict[str, Callable[..., Any]] = {}


def placement_heuristic(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _HEURISTICS[name] = fn
        return fn

    return deco


def known_heuristics() -> list[str]:
    return sorted(_HEURISTICS.keys())


def call_heuristic(name: str, *args: Any, **kwargs: Any) -> Any:
    return _HEURISTICS[name](*args, **kwargs)
