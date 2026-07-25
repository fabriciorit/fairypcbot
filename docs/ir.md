# fairypcbot neutral IR

The IR (intermediate representation) is the contract between elaboration/placement (stages 3-4) and
the emitters (stage 5). **No EasyEDA (or any CAD) concept leaks in here** — this is an
architectural rule, not a suggestion (spec, section 6.1).

The IR is made up of three JSON artifacts written to `build/` and an in-memory object
(`EmitInput`) that combines them with the chosen placement candidate:

```
intent.yaml → validate → elaborate ──┬─→ build/netlist.json   (fairypcbot.schemas.ir.Netlist)
                                      └─→ build/rules.json     (fairypcbot.schemas.ir.RulesDoc)
                          → place    ──── build/placement.json (fairypcbot.schemas.placement.PlacementResult)
                          → emit     ──── EmitInput(netlist, rules, candidate) → target CAD file
```

## `netlist.json` — `schemas.ir.Netlist`

```jsonc
{
  "board": { "layers": 2, "outline": {"shape": "rect", "width_mm": 40, "height_mm": 30}, "mounting_holes": [...] },
  "parts": {
    "U1": {
      "designator": "U1",
      "class_id": "mcu.riscv.ch32v203",   // null if the class couldn't be resolved
      "part_id": "lcsc:C77964",            // null if the designator uses `class:` instead of `part:`
      "package": "LQFP-48",
      "params": { "vdd_range_v": [2.7, 5.5] },
      "pins": { "vdd": [9, 24, 48], "vss": [8, 23, 47], "swdio": 34, "...": "..." },
      "footprint": null                     // Footprint (real pads) when catalog fetch brought geometry
    }
  },
  "nets": {
    "V3V3": { "name": "V3V3", "members": [{"designator": "U3", "pin": "vout"}, {"designator": "U1", "pin": "vdd"}] }
  }
}
```

Built by `elaborate/netlist.py::build_netlist`. `pins` comes from the `pinout` of the object
descriptor (`library/parts/*.yaml`) when the designator uses `part: lcsc:...` and the descriptor
exists; it's empty (`{}`) when the designator uses only `class:` (logical roles exist on the class,
but with no mapping to a physical pin) or when the referenced `part:` has no descriptor in the
library (stub-aware — see `docs/limitations.md`).

`footprint` (`schemas.footprint.Footprint`) is **real** pad geometry (position/size/hole), present
only when `catalog fetch` was able to extract it from the EasyEDA API. The placer
(`place/package_size.py::part_size_mm`) and the emitters prefer that geometry over the
package-name-based estimate when it exists.

## `rules.json` — `schemas.ir.RulesDoc`

```jsonc
{
  "intents": [
    {"type": "power_rail", "net": "V3V3", "voltage_v": 3.3, "max_current_a": 0.5},
    {"type": "decouples", "part": "C1", "target": "U1.vdd", "max_distance_mm": 3}
  ],
  "inherited_rules": [
    {"designator": "C1", "rule": {"type": "domain_atomic", "detail": {}}}
  ]
}
```

`intents` aggregates the `intents[]` from `intent.yaml` (root plus imported blocks).
`inherited_rules` comes from the `rules:` declared in class descriptors
(`library/classes/*.yaml`), resolved along the `extends` chain (`registry/class_resolver.py`) —
today only `domain_atomic` is structurally recognized, but the field is open to new rule types.

The `type` vocabulary in `intents` is the same extensible registry described in the spec (section
3.1): `power_rail`, `diff_pair`, `decouples`, `high_current`, `analog_sensitive`,
`current_loop_minimize` (this last one only appears inside `application_circuit.intents`, section
3.4). See `registry/intents.py::known_intent_types()`.

## `placement.json` — `schemas.placement.PlacementResult`

```jsonc
{
  "outline": {"shape": "rect", "width_mm": 40, "height_mm": 30},
  "candidates": [
    {
      "heuristic": "compact",
      "cost": 170.0,
      "parts": {"U1": {"x_mm": 12.0, "y_mm": 19.0, "rotation_deg": 0, "mirror": false, "layer": 1}},
      "domains": [{"id": "C1+J1+U1", "members": ["C1", "J1", "U1"], "atomic": true, "region_pref": null, "anchor": "edge_south", "orientation": "outward"}],
      "warnings": ["Distance between 'C1+J1+U1' and 'C2+U2' (20.0mm) exceeds max_distance_mm=15.0mm"]
    }
  ]
}
```

1 to 3 candidates (one per registered heuristic: `compact`, `spread`, `thermal_first`), ordered by
ascending `cost`. `warnings` covers both proximity violations (`near`/`max_distance_mm`) and
legalization issues (overlap, out of outline, mounting-hole clearance intrusion) — none of it
discards the candidate (non-blocking MVP behavior — see `docs/limitations.md`).

`domains` is the list of derived domains (`place/domains.py`) used to generate that candidate —
flat in this version, with no subdomain hierarchy (see `docs/limitations.md`).

## `EmitInput` (not serialized — built in memory by `emit`)

```python
@dataclass
class EmitInput:
    netlist: Netlist
    rules: RulesDoc
    candidate: PlacementCandidate  # one item from placement.json, chosen via --heuristic
```

This is what an `Emitter.emit(ir: EmitInput, outdir: Path) -> EmitReport` receives
(`emit/base.py`). `EmitReport.degradations` lists, per designator, what couldn't be faithfully
represented in the target format — today that's almost always `NO_REAL_FOOTPRINT` when a part has
no real pad geometry (see `docs/limitations.md`).

## Why this separation matters

Each artifact has a clear owner and consumer:

- `netlist.json`/`rules.json` are the output of `elaborate` — they know nothing about position.
- `placement.json` is the output of `place` — it knows position, but nothing about CAD format.
- An emitter only ever sees `EmitInput` — it cannot "go back" and read `intent.yaml` or
  reimplement placement logic. This is what guarantees that swapping an emitter (or adding a new
  one) never requires changing `elaborate/` or `place/`, and vice versa (spec, section 0, item 3:
  "a compiler with a neutral IR").
