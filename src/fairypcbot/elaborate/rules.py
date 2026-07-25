"""Builds `rules.json` (spec section 4): expanded intents + rules inherited from classes."""

from __future__ import annotations

from typing import Any

from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.intent import PartSpec, SchematicConfig
from fairypcbot.schemas.ir import InheritedRule, RulesDoc
from fairypcbot.validate.library import LibraryIndex, class_id_for
from fairypcbot.validate.loader import ProjectGraph


def _all_intents(graph: ProjectGraph) -> list[Any]:
    intents = list(graph.root.intents)
    for block in graph.blocks:
        intents.extend(block.intent.intents)
    return intents


def build_rules(
    graph: ProjectGraph, combined_parts: dict[str, PartSpec], library: LibraryIndex
) -> RulesDoc:
    inherited: list[InheritedRule] = []
    for designator, spec in combined_parts.items():
        class_id = class_id_for(designator, spec, library)
        if class_id is None or not library.has_class(class_id):
            continue
        try:
            resolved = resolve_class(class_id, loader=library.get_class)
        except (ClassExtendsCycleError, ClassNotFoundError):
            continue
        for rule in resolved.rules:
            inherited.append(InheritedRule(designator=designator, rule=rule))

    # `schematic:` only from the root intent (same pattern as `board:`, see elaborate/netlist.py) —
    # an imported block should not change the top-level project's knobs.
    schematic = graph.root.schematic if graph.root.schematic is not None else SchematicConfig()
    return RulesDoc(intents=_all_intents(graph), inherited_rules=inherited, schematic=schematic)
