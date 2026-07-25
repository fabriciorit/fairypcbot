# fairypcbot — Specification v0.1

**A text-driven PCB construction framework, LLM-operated, with formal validation and domain-based placement.**

Identity: the project's mascot is **Fae the fairy** — the voice of audit reports and the CLI. The main command installs as `fairypcbot` with the short alias **`fae`** (use `fae` throughout documentation and examples). PyPI package: `fairypcbot`.

Code language: Python ≥3.11. Documentation and message language: English. Code identifier names: English.

---

## 0. Architectural thesis (read before coding)

fairypcbot inverts the premise of existing EDA-as-code tools (atopile, SKiDL):

> **The LLM is the author. The framework is the verifier and materializer. The user is the arbiter.**

Design consequences:

1. No new language exists. All input is YAML validated by JSON Schema (via pydantic). All behavior (component math, heuristics) is Python registered in registries.
2. The LLM **never touches geometry directly**. It writes readable *constraints* in YAML; the framework materializes them into coordinates. The user reviews constraints, not coordinates.
3. The framework is a **compiler with a neutral IR**: front-end (intents → netlist + rules) → middle-end (domain-based placement) → back-ends (emitters). EasyEDA is the *reference* emitter, never a conceptual dependency.
4. Every step is **auditable via structured logs**: intent → decision → artifact, always traceable.
5. Every layer has isolated value (electrical linter, netlist generator, placer, emitters). The project delivers incremental value.

Anti-goals (NOT to implement): a routing engine of its own; SPICE simulation; an interactive GUI (v0.x uses static SVG plus text editing); support for the `.ato` language.

---

## 1. Repository structure

```
fairypcbot/
├── pyproject.toml            # hatchling or setuptools; deps: pydantic>=2, ruamel.yaml, typer, rich, jinja2
├── README.md
├── docs/
├── src/fairypcbot/
│   ├── cli.py                # typer: init, validate, elaborate, place, emit, render, audit
│   ├── schemas/              # pydantic models (source of the JSON Schemas)
│   │   ├── intent.py
│   │   ├── component_class.py
│   │   ├── component_part.py
│   │   ├── domain.py
│   │   ├── rules.py
│   │   └── ir.py
│   ├── registry/             # function registries
│   │   ├── models.py         # @component_model("mosfet.level1") etc.
│   │   └── heuristics.py     # @placement_heuristic("compact") etc.
│   ├── elaborate/            # Stages 2-3: resolution, netlist, electrical linter
│   ├── place/                # Stage 4: domains, floorplan, placement
│   ├── emit/                 # Stage 5: emitters
│   │   ├── base.py           # ABC Emitter — multi-CAD contract
│   │   ├── easyeda_std.py
│   │   └── specctra_dsn.py
│   ├── render/                # static SVG of the positioned board
│   ├── audit/                # logging/audit system (section 8)
│   └── catalog/              # LCSC resolution (part number → descriptor stub)
├── library/
│   ├── classes/              # component class descriptors (YAML)
│   └── packages/             # generic footprints (IPC-7351 nominal, YAML)
├── examples/
│   ├── led_blinker_555/      # offline example (555 timer, class-only, no network)
│   └── metal_detector_bfo/   # analog BFO metal detector (requires catalog fetch)
└── tests/
```

User project convention (created by `fairypcbot init`):

```
my_project/
├── intent.yaml               # 1 per directory; nested directories = reusable blocks
├── blocks/
│   └── power_supply/intent.yaml
├── build/                    # generated artifacts (netlist.json, rules.json, placement.json, *.svg, emitter outputs)
└── audit/                    # logs (section 8)
```

---

## 2. Pipeline stages (contract per command)

| Stage | Command | Input | Output | Failure feeds back to |
|---|---|---|---|---|
| 1. Intent | (LLM/user write it) | — | `intent.yaml` | — |
| 2. Validation | `fairypcbot validate` | intent.yaml + library | structured JSON errors | LLM (fixes YAML) |
| 3. Elaboration | `fairypcbot elaborate` | valid intent | `netlist.json` + `rules.json` + electrical linter report | LLM/user |
| 4. Placement | `fairypcbot place` | netlist + rules | `placement.json` (1–3 candidates) + SVG | LLM (relaxes constraints) |
| 5. Emit | `fairypcbot emit --target easyeda_std\|specctra` | full IR | importable file | — |
| 5b. Oracle | `fairypcbot routecheck` | DSN | Freerouting headless report | stage 4 (fine-grained) |
| 6. End | — | — | user routes in the CAD tool | — |

Roundtrip golden rule: **text is the source of truth up to placement; routing and manual touch-ups belong to the destination CAD tool.** Positions fixed manually are preserved in `placement.lock.yaml` (analogous to a lockfile) and respected on regeneration.

---

## 3. Schemas (Stage 1) — pydantic v2

Implement as pydantic models; export JSON Schema via `fairypcbot schema <name>` (the LLM consumes that schema to generate conformant YAML).

### 3.1 `intent.yaml` (normative skeleton)

```yaml
fairypcbot: "0.1"            # schema version, required
kind: board                 # board | block
name: led_blinker_555
description: >
  Classic LED blinker with a 555 timer in astable mode.

board:                      # kind: board only
  layers: 2
  outline:                  # board geometry
    shape: rect             # rect | circle | polygon | dxf_ref
    width_mm: 40
    height_mm: 18
    corner_radius_mm: 2
  mounting_holes:
    - {x_mm: 3, y_mm: 3, drill_mm: 2.2}

imports:                    # reusable blocks
  - path: blocks/power_supply

parts:                      # instances
  U1:
    part: lcsc:C77964       # catalog resolution (default)
    # OR class-only, if the user explicitly opts in:
    # class: mcu.riscv.ch32v203
    params: {package: QFN28}
  J1:
    part: lcsc:C165948      # USB-C 16P
  # ... the framework expands application circuits via class templates

nets:
  VBUS: [J1.VBUS, PS1.VIN]
  CAN_H: [U2.CANH, J2.1]

intents:                    # electrical intents — closed vocabulary, extensible via registry
  - {type: power_rail, net: VBUS, voltage: 5.0, max_current_a: 0.5}
  - {type: diff_pair, nets: [CAN_H, CAN_L], impedance_ohm: 120}
  - {type: decouples, part: C3, target: U1.VDD, max_distance_mm: 3}
  - {type: high_current, net: SW_NODE, current_a: 2}
  - {type: analog_sensitive, nets: [ADC_IN]}

placement_hints:            # readable constraints (the LLM writes this, never coordinates)
  - {part: J1, anchor: edge_south, orientation: outward}
  - {part: J2, anchor: edge_north}
  - {domain: power_supply, region_pref: west}
  - {part: Y1, near: U1, max_distance_mm: 8}
```

Stage 2 validations (error messages in JSON with `path`, `code`, `message`, `suggestion` — designed for LLM consumption):

- cross-references (parts/nets/imports exist);
- pins exist on the component descriptor;
- intents reference valid entities and have parameters of the correct type;
- forbidden import cycles;
- designator uniqueness across imports (per-block namespace: `power_supply.C1`).

### 3.2 **Class** descriptor (`library/classes/*.yaml`)

Two required levels (class → object), optional `extends` for families. Inheritance = deep dictionary merge, no diamond inheritance.

```yaml
fairypcbot: "0.1"
kind: component_class
id: inductor.power
extends: passive.two_terminal        # optional
pins:
  - {role: terminal, count: 2, separable: false}
params:
  required: [inductance_h, i_sat_a, dcr_ohm]
  optional: [shielded]
models:                              # reference to Python functions by name (registry)
  ripple_current: inductor.ripple_basic
rules:                               # universal rules of the class
  - {type: domain_atomic}            # the 2 pins never separate
application_circuit: null            # IC classes have templates; see 3.4
```

```yaml
kind: component_class
id: mosfet.n_channel
pins:
  - {name: G, role: gate}
  - {name: D, role: drain}
  - {name: S, role: source}
params:
  required: [vth_v, rds_on_ohm, qg_c, vds_max_v, id_max_a]
models:
  iv_curve: mosfet.level1            # registered Python function
  gate_charge_loss: mosfet.qg_switching_loss
```

### 3.3 **Object** descriptor (`library/parts/*.yaml`)

```yaml
fairypcbot: "0.1"
kind: component_part
id: lcsc:C77964
class: mcu.riscv.ch32v203
mpn: CH32V203C8T6
manufacturer: WCH
package:
  name: LQFP-48
  source: easyeda            # footprint resolved via catalog (see 7)
pinout:                      # maps physical pins → class roles
  VDD: [9, 24, 48]
  PA11: 33
params:
  vdd_range_v: [2.7, 5.5]
datasheet_url: "..."
```

`fairypcbot catalog fetch lcsc:C77964` generates a descriptor *stub* from LCSC/EasyEDA data (symbol, footprint, attributes), leaving `class` and `pinout` for the LLM to complete from the datasheet — always with a provenance log entry (section 8).

### 3.4 Application circuits (class templates)

Classes of regular ICs (bucks, LDOs, transceivers, MCUs) declare their application circuit as a **parametric template**:

```yaml
application_circuit:
  parts:
    L1: {class: inductor.power, sizing: buck.inductor_sizing}   # registered function sizes it
    CIN: {class: capacitor.ceramic, sizing: buck.cin_sizing}
    COUT: {class: capacitor.ceramic, sizing: buck.cout_sizing}
  nets_internal: [SW_NODE]
  intents:
    - {type: current_loop_minimize, parts: [SELF, L1, COUT], priority: critical}
  domain:
    atomic: false
    split_cost: high         # subdivision is allowed, but costly (see 5.2)
```

Sizing functions live in Python (`registry/models.py`), receive context params (Vin, Vout, Iout, f_sw) and return values plus a textual justification (for the audit log).

---

## 4. Elaboration and electrical linter (Stage 3)

`fairypcbot elaborate` produces:

1. **`netlist.json`** — a neutral netlist (a format of its own, documented in `docs/ir.md`): resolved parts (class+object+package), nets, attributes.
2. **`rules.json`** — expanded intents plus rules inherited from classes plus application circuits.
3. **Electrical linter report** (the project's immediate differentiator; no free CAD tool does this):
   - per-net current budget vs. capacity (trace width estimated via simplified IPC-2152);
   - power tree (every VDD reaches a source; voltage-domain detection);
   - logic-level compatibility between domains (3V3 ↔ 5V without a level shifter ⇒ warning);
   - floating required pins (EN, VREF, thermal pad);
   - missing decoupling per IC power pin;
   - checks registrable via `@electrical_check("name")` — planned extensibility.

Severities: `error` (blocks), `warning`, `info`. JSON output plus `rich` terminal rendering.

---

## 5. Domain-based placement (Stage 4) — the core

### 5.1 Data model

**Domain** = a tree node, with:

- members (parts and/or subdomains);
- atomicity (`atomic: true` ⇒ indivisible) or `split_cost` (low/med/high/critical) — subdividing domains is allowed with an explicit cost in the optimizer;
- region attributes: layer(s), region preference (N/S/E/W/center), edge anchors, orientation, vertical keepouts (`no_route_under`, `ground_pour_under`);
- optional internal geometric template (regular leaf domains — buck, crystal+caps — have near-deterministic geometry dictated by best practices: implement as `@domain_template("buck.standard")` functions).

Domains are derived automatically from: (a) application circuits; (b) intents (`decouples` creates a pin+cap domain; `diff_pair` groups); (c) user/LLM `placement_hints`. Connectivity graph between domains = edges weighted by number of nets × criticality.

### 5.2 Algorithm (MVP — 2-layer boards, low/medium density)

1. Resolve internal geometry of leaf domains (parametric templates → bounding boxes with interface pins).
2. Floorplan of top-level domains: small-space search (slicing tree or coarse grid + light annealing), cost = Σ(estimated inter-domain net length × weight) + region/anchor violations + subdivision costs used.
3. Legalization: no overlap, package clearances, respect for outline and holes.
4. Generate **2–3 candidates** with distinct registered heuristics: `compact`, `spread`, `thermal_first`.
5. Per-candidate output: `placement.json` (designator → x, y, rotation, mirror, layer) + `board_outline` + SVG.

A routability failure (5b) does **not** immediately discard the candidate: first a fine-grained relaxation pass — loosen regional clearance, allow a domain to be subdivided, expand the outline if the user allowed it (`outline.growable: true`). Only then move on to the next candidate.

### 5.3 Render and user review

`fairypcbot render` → static SVG: outline, packages (silhouette + designator), color-coded domains with a legend, anchors, optional ratsnest (`--ratsnest`). The user comments *in text*; the LLM translates that into edits to `placement_hints` or to `placement.lock.yaml` (fixed positions). If a fixed position violates a domain, `fairypcbot place` emits a warning with an explanation and the cost incurred — guide without locking things down.

---

## 6. IR and emitters (Stage 5)

### 6.1 Neutral IR

The IR is the set `{netlist.json, rules.json, placement.json, outline}` — **no EasyEDA concept may leak into it**. Architecture test: both MVP emitters consume exactly the same IR.

### 6.2 Emitter contract (`emit/base.py`)

```python
class Emitter(ABC):
    id: str                       # "easyeda_std", "specctra_dsn", eventually "kicad", "easyeda_pro"
    def capabilities(self) -> EmitterCaps: ...   # max layers, supported rules, etc.
    def emit(self, ir: IR, outdir: Path) -> EmitReport: ...
    # EmitReport lists IR rules NOT representable in the target (explicit, logged degradation)
```

### 6.3 EasyEDA Std emitter (reference)

- Format: EasyEDA Standard JSON (also importable into Pro). The subset used is documented in `docs/easyeda_format.md`, based on community-known reverse engineering (easyeda2kicad as an engineering reference).
- Footprints/symbols: resolved by LCSC ID via the public EasyEDA API (same route as easyeda2kicad); local cache at `~/.cache/fairypcbot/`.
- Emits: a board with positioned components + nets (ratsnest) + outline + holes + basic DRC rules (clearance, minimum width per net class). Routing is left to EasyEDA's autorouter (known limitation: no headless API — the iteration loop with EasyEDA is user-assisted).

### 6.4 Specctra DSN emitter (routability oracle)

- Emits standard DSN; `fairypcbot routecheck` invokes **Freerouting headless** (Java CLI) and interprets the result: complete routes? vias? iterations? per-region failures?
- The report feeds back into stage 4 (section 5.2). Routability in Freerouting is used as a *predictor* — the user's final routing happens in the destination CAD tool.

---

## 7. Component catalog

- Universal primary key: **LCSC part number** (`lcsc:CXXXXX`). Secondary sources (Digikey, Mouser, direct MPN) enter as future *resolvers* with the same contract (`catalog/base.py`).
- `catalog fetch` never fabricates data: fields not obtained stay `null` with a `provenance: missing` marker, and the report instructs the LLM to complete them from the datasheet (with the URL recorded).
- Every piece of data has provenance: `provenance: {source: easyeda_api|datasheet|llm|user, ref: url_or_hash, timestamp}`.

---

## 8. Audit and logging system (first-class requirement)

**Goal: full traceability from intent → decision → artifact.** Auditing is not debug logging; it is a structured record of decisions.

### 8.1 Architecture

- An `audit/` directory in the user's project; one **JSONL** file per run: `audit/2026-07-19T14-30-12_place.jsonl`.
- Each line = an event with a fixed schema (`schemas/audit.py`):

```json
{
  "ts": "2026-07-19T14:30:12.345Z",
  "run_id": "uuid",
  "phase": "place",
  "actor": "framework|llm|user",
  "event": "decision|artifact|validation|external_call|prompt|error",
  "code": "placement.domain_split",
  "summary": "Domain power_supply subdivided: COUT moved to region east",
  "detail": {"cost_incurred": "high", "reason": "CAN_H routability"},
  "inputs": [{"path": "intent.yaml", "sha256": "..."}],
  "outputs": [{"path": "build/placement.json", "sha256": "..."}]
}
```

### 8.2 Rules

1. **Hash every artifact** consumed and produced (sha256) on every event that touches them — allows proving that a given `placement.json` derived from a specific `intent.yaml`.
2. **Justified decisions**: every non-deterministic choice (heuristic chosen, dimensioned value, relaxed constraint, rule degraded by an emitter) generates a `decision` event with a readable `reason`. Sizing functions return `(value, justification)` for exactly this purpose.
3. **LLM interactions**: the framework does not call an LLM directly (the LLM operates *on* the framework as an external agent), but it offers `fairypcbot audit note --actor llm --summary "..."` so the LLM can log its own decisions on the same trail; implementation conventions (see section 10) instruct the model to do so for every relevant decision.
4. **User requests**: `fairypcbot audit note --actor user ...` likewise; in addition, `validate/elaborate/place/emit` automatically log a snapshot (hash) of all input YAMLs.
5. **Can be disabled for performance**: `--no-audit` or `audit: false` in the intent; default is **on**. Even when disabled, `error` events are always recorded.
6. **Querying**: `fairypcbot audit show [--run ID] [--phase X] [--actor llm]` renders a readable timeline; `fairypcbot audit trace build/placement.json` reconstructs an artifact's derivation chain (provenance graph via hashes).
7. Conventional (technical-level) debug logs use Python's standard `logging`, kept separate from the audit trail; `-v/-vv` controls verbosity.

---

## 9. Implementation roadmap (mandatory, incremental order)

Each milestone must end with passing tests and a working example — deliverable value per step.

- **M1 — Foundation**: repo skeleton, pydantic schemas (intent, class, object), `validate` with structured errors, audit system (8), typer CLI. Test: a reference intent validates; deliberate errors produce a useful error JSON.
- **M2 — Catalog + founding library**: `catalog fetch` (LCSC/EasyEDA API), ~29 founding classes (resistor, ceramic/electrolytic/trimmer capacitor, power inductor, LED, diode/Schottky, NPN/PNP BJT, N/P MOSFET, crystal, potentiometer, speaker, SPST/SPDT/DPDT switch, timer 555, audio amp LM386, op-amp, LDO, switching regulator, MCU CH32V203, USB-C connector, JST/terminal/header/battery connectors). Application circuits for LDO, MCU (decoupling+crystal).
- **M3 — Elaboration + electrical linter**: netlist.json, rules.json, the 5 checks from section 4. Test: the reference example elaborates cleanly; a circuit with a deliberate error (3A net on a default-width trace, floating VDD) is caught.
- **M4 — Domains + placement**: domain derivation, domain templates (buck, crystal, decoupling), floorplan, legalization, 3 heuristics, `placement.json`, SVG render. Visual test: the reference example SVG looks plausible.
- **M5 — Emitters**: base.py, EasyEDA Std, EasyEDA Pro, Specctra DSN, `routecheck` with Freerouting headless. MVP acceptance test: **end-to-end — intent → validate → elaborate → place → emit → routecheck**.
- **M6 — Polish for publication**: README with the illustrated end-to-end example, docs/ir.md, docs/easyeda_format.md, CI (pytest + validation of library YAMLs), license (MIT or Apache-2.0).

Post-MVP (not to implement now, but not to block architecturally): KiCad emitter (`kiutils`), EasyEDA Pro emitter, Digikey/Mouser resolvers, RF/antenna/thermal/skin-effect constraints as new intent types + checks, 4 layers, interactive visualization.

---

## 10. Implementation conventions

1. Work milestone by milestone, in order. Don't anticipate features from future milestones.
2. Tests with pytest from M1 onward; every schema has acceptance and rejection tests. Validator coverage takes priority over overall coverage.
3. Every error message aimed at the user/LLM: English, with a stable `code`, the `path` in the YAML, and an actionable `suggestion`.
4. Never hardcode EasyEDA concepts outside `emit/easyeda_std.py` and `catalog/` — review this on every change.
5. Log relevant implementation decisions via `fairypcbot audit note --actor llm` when operating on example projects; for the framework's own architecture decisions, keep short decision records documenting the rationale.
6. Dependencies: minimal. pydantic, ruamel.yaml, typer, rich, jinja2 (emitters), svgwrite (render). Freerouting is an optional external dependency (Java), detected at runtime.
7. External APIs (EasyEDA/LCSC): always with local cache, timeout, and graceful fallback (`provenance: missing` stub).
8. Code style: ruff plus full type hints; mypy in strict mode on the schemas and the IR.
9. In case of ambiguity in this spec, prefer the simplest solution that preserves the neutral IR and the audit trail — and record the open question for later resolution.
