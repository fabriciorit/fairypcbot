"""Specctra DSN emitter — routability oracle via Freerouting (spec section 6.4).

**Confidence**: the DSN format itself is a stable public specification (Specctra Design File),
unlike EasyEDA Std (reverse engineered) — higher structural confidence here. What remains
best-effort/not validated live is (a) pad geometry coming from EasyEDA (see the documentation) and (b) the
exact Freerouting CLI used by `emit/routecheck.py` (see the documentation).

Each designator becomes its own `image` in the `library` (no deduplication of repeated
footprints — an acceptable simplification for the MVP; a project with many instances of the same
footprint produces a DSN larger than strictly necessary, but still valid).
"""

from __future__ import annotations

from pathlib import Path

from fairypcbot.emit.base import DegradedItem, EmitCapabilities, EmitInput, EmitReport, Emitter
from fairypcbot.place.geometry import outline_bbox
from fairypcbot.place.package_size import footprint_bounds, part_size_mm

_DSN_SHAPE = {"rect": "rect", "oval": "oval", "ellipse": "round", "polygon": "rect"}


def _image_name(designator: str) -> str:
    return f"fp_{designator}"


def _sexpr_pin(pad_shape: str, w_mm: float, h_mm: float, number: str, x_mm: float, y_mm: float) -> str:
    dsn_shape = _DSN_SHAPE.get(pad_shape, "rect")
    if dsn_shape == "round":
        radius = max(w_mm, h_mm) / 2
        return f'    (pin round {radius:.4f} "{number}" {x_mm:.4f} {-y_mm:.4f})'
    return f'    (pin {dsn_shape} {w_mm:.4f} {h_mm:.4f} "{number}" {x_mm:.4f} {-y_mm:.4f})'


def _library_image(designator: str, ir_netlist_part, footprint) -> tuple[str, list[str]]:
    """Returns (`(image ...)` block, list of emitted pin numbers)."""
    lines = [f'  (image "{_image_name(designator)}"']
    pin_numbers: list[str] = []

    if footprint and footprint.pads:
        bounds = footprint_bounds(footprint)
        assert bounds is not None
        x0, y0, x1, y1 = bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lines.append(f"    (outline (rect signal {x0 - cx:.4f} {-(y1 - cy):.4f} {x1 - cx:.4f} {-(y0 - cy):.4f}))")
        for pad in footprint.pads:
            lines.append(_sexpr_pin(pad.shape, pad.width_mm, pad.height_mm, pad.number, pad.x_mm - cx, pad.y_mm - cy))
            pin_numbers.append(pad.number)
    else:
        w, h = part_size_mm(ir_netlist_part.package if ir_netlist_part else None, None)
        lines.append(f"    (outline (rect signal {-w / 2:.4f} {-h / 2:.4f} {w / 2:.4f} {h / 2:.4f}))")
        lines.append(_sexpr_pin("rect", w, h, "1", 0.0, 0.0))
        pin_numbers.append("1")

    lines.append("  )")
    return "\n".join(lines), pin_numbers


class SpecctraDsnEmitter(Emitter):
    id = "specctra_dsn"

    def capabilities(self) -> EmitCapabilities:
        return EmitCapabilities(max_layers=2, supports_rules=["clearance", "trace_width"])

    def emit(self, ir: EmitInput, outdir: Path) -> EmitReport:
        outdir.mkdir(parents=True, exist_ok=True)
        degradations: list[DegradedItem] = []

        outline = ir.netlist.board.outline if ir.netlist.board else None
        w, h = outline_bbox(outline) if outline else (40.0, 40.0)

        placement_lines = ['  (placement']
        library_blocks = []
        pin_numbers_by_designator: dict[str, list[str]] = {}
        has_real_footprint: dict[str, bool] = {}

        for designator, placement in ir.candidate.parts.items():
            part = ir.netlist.parts.get(designator)
            footprint = part.footprint if part else None
            block, pin_numbers = _library_image(designator, part, footprint)
            library_blocks.append(block)
            pin_numbers_by_designator[designator] = pin_numbers
            has_real_footprint[designator] = bool(footprint and footprint.pads)

            if not has_real_footprint[designator]:
                degradations.append(
                    DegradedItem(
                        designator=designator,
                        code="NO_REAL_FOOTPRINT",
                        reason=(
                            "No real pad geometry — emitted a single placeholder pin "
                            "covering the estimated bounding box; real routing is not possible"
                        ),
                    )
                )

            placement_lines.append(
                f'    (component "{_image_name(designator)}"\n'
                f'      (place {designator} {placement.x_mm:.4f} {-placement.y_mm:.4f} front 0)\n'
                f"    )"
            )
        placement_lines.append("  )")

        network_lines = ["  (network"]
        for net_name, net in ir.netlist.nets.items():
            pin_refs = []
            for member in net.members:
                if not member.pin:
                    continue
                if has_real_footprint.get(member.designator):
                    # Part with real geometry: uses the exact physical pin for this net's role
                    # (ResolvedPart.pins), not a match by numeric coincidence.
                    part = ir.netlist.parts.get(member.designator)
                    physical = part.pins.get(member.pin) if part else None
                    if physical is None:
                        continue
                    values = physical if isinstance(physical, list) else [physical]
                    available = set(pin_numbers_by_designator.get(member.designator, []))
                    pin_refs.extend(
                        f"{member.designator}-{v}" for v in values if str(v) in available
                    )
                else:
                    # Placeholder: a single pin represents the entire part (degradation already
                    # recorded) — appears in every net that touches it, with no role distinction.
                    pin_refs.extend(
                        f"{member.designator}-{num}"
                        for num in pin_numbers_by_designator.get(member.designator, [])
                    )
            if pin_refs:
                network_lines.append(f'    (net "{net_name}" (pins {" ".join(pin_refs)}))')
        network_lines.append("  )")

        doc = "\n".join(
            [
                '(pcb "fairypcbot_export"',
                "  (parser",
                '    (string_quote ")',
                '    (host_cad "fairypcbot")',
                '    (host_version "0.1")',
                "  )",
                "  (resolution mm 1000000)",
                "  (unit mm)",
                "  (structure",
                "    (layer top (type signal))",
                "    (layer bottom (type signal))",
                f"    (boundary (rect pcb 0 0 {w:.4f} {h:.4f}))",
                "  )",
                *placement_lines,
                "  (library",
                *library_blocks,
                "  )",
                *network_lines,
                "  (wiring)",
                ")",
            ]
        )

        out_path = outdir / "board.dsn"
        out_path.write_text(doc, encoding="utf-8")

        return EmitReport(emitter_id=self.id, output_path=str(out_path), degradations=degradations)
