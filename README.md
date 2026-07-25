# fairypcbot 🧚

Intent-driven PCB design framework — describe what your board must do, let automation handle
the rest.

> **Experimental project.** The outputs of this tool have not been independently validated for
> fabrication. Do not rely on them for safety-critical applications or any use case that requires
> guarantees of correctness, quality, or performance.

> The LLM is the author of constraints in YAML. The framework validates and materializes them
> into geometry. The user has the final say.

Mascot: **Fae the fairy** — voice of the audit reports and the CLI.
Main command: `fairypcbot`, short alias: **`fae`**.

## Why this exists

I grew tired of the workflow where an LLM helps design a PCB but the human still burns hours on
editing minutiae, obscure scripting languages, and vendor-specific format quirks. I wanted something
simpler: a tool comfortable enough that *any* LLM capable of understanding the system can supply the
hints needed to build engineering-oriented PCBs, adapted to what the user actually needs.

It has been useful in my own projects. I hope it is useful to others too.

*— Fabrício Ribeiro Toloczko*

## Status

Milestones M1–M5 of the roadmap are implemented:

| Stage | Command | What it does |
|---|---|---|
| 1. Intent | — | You (or the LLM) write `intent.yaml` |
| 2. Validation | `fae validate` | Checks references, pins, import cycles, intent types |
| 3. Elaboration | `fae elaborate` | Generates `netlist.json` + `rules.json` and runs the electrical linter |
| 4. Placement | `fae place` / `fae render` | Derives domains, generates 1–3 layout candidates + SVG |
| 5. Emission | `fae emit` / `fae routecheck` | Materializes into EasyEDA Std/Pro or Specctra DSN |
| — | `fae catalog fetch` | Resolves a component via the public EasyEDA API (LCSC) |
| — | `fae audit show/trace/note` | Queries the audit trail from intent to decision to artifact |

**Before trusting the output for fabrication**, read
[`docs/limitations.md`](docs/limitations.md): without real pad geometry (obtained via
`catalog fetch`), the output is a *placement preview*, not a routable board. This is reported
explicitly on every `emit` run as a per-part degradation.

## Installation (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `fairypcbot` and `fae` commands in the virtual environment.

## Quick guide: from zero to a placement

```bash
# 1. create the structure of a new project
fae init fairy_project
cd fairy_project

# 2. edit intent.yaml (you or an LLM) — see examples/ for reference

# 3. validate
fae validate

# 4. elaborate (netlist + electrical linter)
fae elaborate

# 5. place (generates candidates + SVG in build/)
fae place

# 6. review build/candidate_*.svg and, if you want, re-render with ratsnest
fae render --heuristic compact --ratsnest

# 7. emit for the target CAD tool
fae emit --target easyeda_std
fae emit --target specctra

# 8. (optional, requires Freerouting installed) routability check
fae routecheck
```

Every command writes events to the audit trail (`audit/*.jsonl`, can be disabled with
`--no-audit`); `fae audit show` shows the timeline.

## Examples

### `led_blinker_555` — offline "hello world"

[`examples/led_blinker_555/`](examples/led_blinker_555/) is a classic 555 timer LED blinker.
It uses only `class:` references from the founding library — no network access or vendor data
required. Serves as the CI smoke test.

```bash
fae validate  -p examples/led_blinker_555
fae elaborate -p examples/led_blinker_555
fae place     -p examples/led_blinker_555
```

### `metal_detector_bfo` — analog showcase

[`examples/metal_detector_bfo/`](examples/metal_detector_bfo/) is a fully analog BFO metal
detector (two Colpitts oscillators + diode mixer + LM386 audio amp). It requires vendor data
obtained via `catalog fetch`:

```bash
cd examples/metal_detector_bfo
fae catalog fetch lcsc:C22438596   # LM386M-1
# ... see examples/metal_detector_bfo/README.md for the full list
fae validate && fae elaborate && fae place
```

## Repository structure

```
fairypcbot/
├── src/fairypcbot/
│   ├── cli.py                  # typer commands
│   ├── schemas/                # pydantic models (intent, class, part, IR, placement...)
│   ├── registry/               # @intent_type, @component_model, @placement_heuristic, extends
│   ├── validate/               # stage 2
│   ├── elaborate/              # stage 3 (netlist/rules + electrical linter)
│   ├── place/                  # stage 4 (domains + floorplan + legalization)
│   ├── render/                 # static SVG
│   ├── emit/                   # stage 5 (EasyEDA Std/Pro, Specctra DSN, routecheck)
│   ├── catalog/                # LCSC/EasyEDA resolution (+ footprint geometry)
│   └── audit/                  # JSONL audit trail
├── library/
│   ├── classes/                # component class descriptors (29 classes, CC0-1.0)
│   └── packages/               # generic footprints — IPC-7351 nominal (CC0-1.0)
├── docs/
│   ├── llm/                    # LLM integration contract (read by `fae llm`)
│   ├── limitations.md          # known limitations by area
│   ├── ir.md                   # IR format (netlist, rules, placement)
│   └── easyeda_format.md       # subset of EasyEDA format used
├── examples/
│   ├── led_blinker_555/        # offline example (class-only, no network)
│   └── metal_detector_bfo/     # analog showcase (requires catalog fetch)
└── tests/
```

## Data and licensing

- **Code**: [Apache-2.0](LICENSE).
- **`library/`**: [CC0-1.0](library/LICENSE). Contains only authorial descriptors (component
  classes and generic packages) — no vendor data.
- **No vendor data is redistributed.** `fae catalog fetch` and `fae datasheet ingest` download
  third-party data **directly to the user's machine** (cached in `~/.cache/fairypcbot/`, outside
  the repository). That data remains subject to the terms of its source (EasyEDA/LCSC,
  manufacturers). **Verifying and complying with those terms is the user's responsibility** — this
  project neither licenses nor warrants third-party data.
- Practical consequence: do not commit library generated by `fetch` into a public repository.
  `examples/*/library/` is already in `.gitignore` for this reason.

## Technical documentation

- [`docs/llm/`](docs/llm/) — LLM integration contract (`fae llm` prints the index)
- [`docs/ir.md`](docs/ir.md) — format of `netlist.json`, `rules.json`, `placement.json`
- [`docs/easyeda_format.md`](docs/easyeda_format.md) — subset of EasyEDA format covered
- [`docs/limitations.md`](docs/limitations.md) — known limitations by area
- [`docs/library_repo.md`](docs/library_repo.md) — library repository structure

## Development

```bash
pytest -m "not network"                              # test suite (offline)
ruff check src tests                                 # lint
mypy src/fairypcbot/schemas src/fairypcbot/registry  # strict type check
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full development guide.
