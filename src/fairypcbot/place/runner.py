"""Phase 4 orchestration (`fairypcbot place`)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fairypcbot.audit.writer import AuditWriter
from fairypcbot.elaborate.runner import elaborate_project
from fairypcbot.place import (
    floorplan as _floorplan_registration,  # noqa: F401 — registers heuristics
)
from fairypcbot.place.autosize import autosize_outline
from fairypcbot.place.domains import compute_thermal_source_designators, derive_domains
from fairypcbot.place.legalize import legalize_candidate
from fairypcbot.place.refine import refine_candidate
from fairypcbot.place.routability import MAX_ACCEPTABLE_RATIO, estimate_routability
from fairypcbot.place.seeds import apply_seeds
from fairypcbot.registry.heuristics import call_heuristic, known_heuristics
from fairypcbot.schemas.errors import ValidationReport
from fairypcbot.schemas.intent import Intent
from fairypcbot.schemas.placement import PlacementCandidate, PlacementResult
from fairypcbot.validate.library import LibraryIndex, resolve_library_paths
from fairypcbot.validate.loader import load_yaml, resolve_imports


@dataclass
class PlaceResult:
    validation: ValidationReport
    placement: PlacementResult | None = None


def place_project(
    project_root: Path, *, no_audit: bool = False, write_artifacts: bool = True
) -> PlaceResult:
    project_root = Path(project_root)

    with AuditWriter(project_root, phase="place", enabled=not no_audit) as writer:
        elab = elaborate_project(project_root, no_audit=no_audit, write_artifacts=write_artifacts)
        if not elab.validation.ok:
            writer.emit(
                actor="framework",
                event="validation",
                code="PLACE_ABORTED_INVALID_INTENT",
                summary="place abortado: intent.yaml não passou na validação (fase 2)",
            )
            return PlaceResult(validation=elab.validation)

        assert elab.netlist is not None and elab.rules is not None
        netlist, rules = elab.netlist, elab.rules

        raw = load_yaml(project_root / "intent.yaml")
        intent = Intent.model_validate(raw)
        graph = resolve_imports(project_root, intent)

        assert intent.board is not None, "place requer kind: board (já garantido pela validação)"
        domains, proximity_hints = derive_domains(graph, netlist, rules)

        library = LibraryIndex(
            resolve_library_paths(project_root, extra_paths=[Path(p) for p in intent.libraries])
        )
        thermal_source_designators = compute_thermal_source_designators(netlist, library)

        if intent.placement_seeds:
            writer.emit(
                actor="framework",
                event="decision",
                code="PLACEMENT_SEEDED",
                summary=f"{len(intent.placement_seeds)} seed(s) de placement aplicado(s) — ver the documentation",
                detail={"designators": list(intent.placement_seeds)},
            )

        declared = intent.board.outline
        auto_mode = declared is None or (declared.growable and declared.shape == "rect")
        if auto_mode:
            # Automatic outline (see the documentation): without declared geometry, searches for the smallest 4:3 rect without

            # blocking warnings — autosize_outline already runs heuristic+refine+legalize internally,

            # so the result comes out ready (do not repeat the loop below). With `growable`, the

            # declared size becomes just the search floor (never results smaller than this).
            autosize = autosize_outline(
                domains, netlist, proximity_hints, thermal_source_designators,
                min_width_mm=declared.width_mm if declared else None,
                min_height_mm=declared.height_mm if declared else None,
                layers=intent.board.layers,
                seeds=intent.placement_seeds,
            )
            outline, candidates = autosize.outline, autosize.candidates
            writer.emit(
                actor="framework",
                event="decision",
                code="PLACEMENT_OUTLINE_AUTOSIZED",
                summary=f"Outline automático: {outline.width_mm}x{outline.height_mm}mm",
                detail={"width_mm": outline.width_mm, "height_mm": outline.height_mm},
            )
        else:
            outline = intent.board.outline
            candidates = []
            for name in known_heuristics():
                candidate: PlacementCandidate = call_heuristic(
                    name, domains, netlist, outline, proximity_hints, thermal_source_designators
                )
                unmatched_seeds = apply_seeds(candidate, intent.placement_seeds)
                for d in unmatched_seeds:
                    candidate.warnings.append(
                        f"placement_seeds['{d}'] não corresponde a nenhuma peça posicionada "
                        f"(designador inexistente ou off_board) — seed ignorado"
                    )
                refine_candidate(candidate, netlist, intent.board, proximity_hints)
                candidate.warnings.extend(legalize_candidate(candidate, netlist, intent.board))
                # Informational warning (see the documentation) — does not block, just warns that the board might be
                # tight for the router even without geometric overlap; explicitly declared outline
                # is a user decision, the framework does not correct it automatically here.
                routability = estimate_routability(candidate, netlist, outline, intent.board.layers)
                if routability.ratio > MAX_ACCEPTABLE_RATIO:
                    candidate.warnings.append(
                        f"Estimativa de roteabilidade: demanda {routability.demand_mm2:.0f}mm² / "
                        f"oferta {routability.supply_mm2:.0f}mm² (razão {routability.ratio:.0%}) "
                        f"— roteamento provavelmente apertado, considere outline maior (não é um "
                        f"roteamento real, ver the documentation)"
                    )
                candidates.append(candidate)
                writer.emit(
                    actor="framework",
                    event="decision",
                    code="PLACEMENT_HEURISTIC_RUN",
                    summary=f"Heurística '{name}': custo={candidate.cost:.2f}, {len(candidate.warnings)} aviso(s)",
                    detail={"heuristic": name, "cost": candidate.cost, "warnings": candidate.warnings},
                )
            candidates.sort(key=lambda c: c.cost)

        result = PlacementResult(outline=outline, candidates=candidates)

        outputs = []
        if write_artifacts:
            build_dir = project_root / "build"
            build_dir.mkdir(parents=True, exist_ok=True)
            placement_path = build_dir / "placement.json"
            placement_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            outputs.append(writer.snapshot_input(placement_path))

        writer.emit(
            actor="framework",
            event="artifact",
            code="PLACE_RUN",
            summary=f"Placement concluído com {len(candidates)} candidato(s)",
            outputs=outputs,
        )

        return PlaceResult(validation=elab.validation, placement=result)
