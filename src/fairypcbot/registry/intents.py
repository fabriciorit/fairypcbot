"""Dynamic registry of `intents` types (spec section 3.1).

The `intents` vocabulary is "closed but extensible": instead of a static `Union[...]` in
`schemas/intent.py` (which would require rewriting the schema on every new milestone), each intent
type registers itself here via `@intent_type("name")`. `schemas/intent.py` builds the discriminated
union by calling `build_intent_union()` after `schemas/intents_builtin.py` has already registered
the built-in types — that is why the import order in `schemas/__init__.py` matters.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from pydantic import BaseModel, Field

_INTENT_MODELS: dict[str, type[BaseModel]] = {}


def intent_type(name: str) -> Callable[[type[BaseModel]], type[BaseModel]]:
    """Decorator that registers a pydantic model as the schema for intent `type: name`."""

    def deco(cls: type[BaseModel]) -> type[BaseModel]:
        _INTENT_MODELS[name] = cls
        return cls

    return deco


def known_intent_types() -> list[str]:
    return sorted(_INTENT_MODELS.keys())


def build_intent_union() -> Any:
    """Builds the discriminated union by `type` from all intents registered so far."""
    if not _INTENT_MODELS:
        raise RuntimeError(
            "No intent type registered. Import fairypcbot.schemas.intents_builtin "
            "before building the union."
        )
    from typing import Union

    models = tuple(_INTENT_MODELS.values())
    if len(models) == 1:
        return Annotated[models[0], Field()]
    return Annotated[Union[*models], Field(discriminator="type")]
