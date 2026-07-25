"""Resolution/merge of `extends` between class descriptors (spec section 3.2).

Decision (see the documentation): `extends` supports only linear single-parent inheritance. Multiple/diamond
inheritance is not detected or resolved — it is forbidden by design, simplifying the merge to
"concatenate/overwrite along a chain", without needing a diamond-resolution algorithm (C3
linearization etc.) that would have no real consumer in M1.
"""

from __future__ import annotations

from typing import Literal, Protocol

from fairypcbot.schemas.component_class import ApplicationCircuit, ComponentClass, PinSpec, RuleRef

ParamsKey = Literal["required", "optional"]


class ClassExtendsCycleError(ValueError):
    def __init__(self, chain: list[str]):
        self.chain = chain
        super().__init__(f"'extends' cycle detected: {' -> '.join(chain)}")


class ClassNotFoundError(ValueError):
    def __init__(self, class_id: str):
        self.class_id = class_id
        super().__init__(f"Class '{class_id}' not found")


class ClassLoader(Protocol):
    def __call__(self, class_id: str) -> ComponentClass: ...


def _load_chain(class_id: str, loader: ClassLoader) -> list[ComponentClass]:
    """Returns the chain [root, ..., class_id] following `extends`, detecting cycles."""
    chain: list[ComponentClass] = []
    seen: list[str] = []
    current_id: str | None = class_id
    while current_id is not None:
        if current_id in seen:
            raise ClassExtendsCycleError([*seen, current_id])
        seen.append(current_id)
        try:
            cls = loader(current_id)
        except KeyError as exc:
            raise ClassNotFoundError(current_id) from exc
        chain.append(cls)
        current_id = cls.extends
    chain.reverse()  # root first
    return chain


def _merge_pins(base: list[PinSpec], child: list[PinSpec]) -> list[PinSpec]:
    def key(p: PinSpec) -> str:
        return p.name or p.role

    merged: dict[str, PinSpec] = {key(p): p for p in base}
    for p in child:
        merged[key(p)] = p  # child overwrites parent with the same key
    return list(merged.values())


def _merge_rules(base: list[RuleRef], child: list[RuleRef]) -> list[RuleRef]:
    return [*base, *child]  # simple concatenation; exact duplicates are harmless


def _merge_application_circuit(
    base: ApplicationCircuit | None, child: ApplicationCircuit | None
) -> ApplicationCircuit | None:
    """Application circuits are additive along the `extends` chain: the decoupling declared in
    `mcu.generic`, for example, must not disappear when `mcu.riscv.ch32v203` adds its own crystal
    circuit — template designators (`C_VDD`, `Y1`, etc.) are already scoped per class, so a name
    collision between base/child is treated as an overwrite (same rule used for `pins`)."""
    if base is None:
        return child
    if child is None:
        return base
    merged_parts = {**base.parts, **child.parts}
    return ApplicationCircuit(
        parts=merged_parts,
        nets_internal=list(dict.fromkeys([*base.nets_internal, *child.nets_internal])),
        intents=[*base.intents, *child.intents],
        domain=child.domain or base.domain,
    )


def resolve_class(class_id: str, loader: ClassLoader) -> ComponentClass:
    """Resolves a class by applying a deep merge along the `extends` chain (root -> leaf)."""
    chain = _load_chain(class_id, loader)
    resolved = chain[0]
    for child in chain[1:]:
        merged_params: dict[ParamsKey, list[str]] = {**resolved.params}
        for key_, names in child.params.items():
            merged_params[key_] = list(dict.fromkeys([*merged_params.get(key_, []), *names]))
        resolved = ComponentClass(
            kind="component_class",
            id=child.id,
            description=child.description or resolved.description,
            extends=child.extends,
            pins=_merge_pins(resolved.pins, child.pins),
            params=merged_params,
            models={**resolved.models, **child.models},
            rules=_merge_rules(resolved.rules, child.rules),
            application_circuit=_merge_application_circuit(
                resolved.application_circuit, child.application_circuit
            ),
        )
    return resolved
