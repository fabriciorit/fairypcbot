# Workflow

## Pipeline

```
intent.yaml → validate → elaborate → place → render → emit → routecheck
```

| Stage | Command | Produces | On failure |
|---|---|---|---|
| 2. Validation | `fae validate` | Structured errors/warnings | Fix `intent.yaml`, validate again |
| 3. Elaboration | `fae elaborate` | `build/netlist.json`, `build/rules.json` + electrical linter | Aborts if validate failed |
| 4. Placement | `fae place` | `build/placement.json` (1-3 candidates) + SVGs | Aborts if elaborate failed |
| 4b. Render | `fae render --heuristic <name> [--ratsnest]` | Re-renders the SVG of an already generated candidate | — |
| 5. Emit | `fae emit --target easyeda_std\|specctra` | File importable into the target CAD | Aborts if `place` hasn't run |
| 5b. Routecheck | `fae routecheck` | Runs Freerouting headless over the DSN | Skips gracefully if Freerouting isn't installed (not an error) |

Each command is independent and can be run multiple times — there is no hidden state between runs
beyond the files in `build/` and `audit/`.

## Before writing `intent.yaml` from scratch

1. `fae init <project>` creates the skeleton (minimal `intent.yaml`, `blocks/`, `build/`, `audit/`).
2. See `examples/led_blinker_555/intent.yaml` as a reference for a complete, valid offline project, or `examples/metal_detector_bfo/intent.yaml` as a complete analog example.
3. Read `intent-authoring.md` before writing `intents`/`nets`/`placement_hints`.

## Correction loop

`fae validate` (and `fae elaborate`) never stop at the first error — all issues found are
returned at once, each with `path`, `code`, `message`, `suggestion`. Fix every item returned
before running again, rather than fixing one and re-running repeatedly.

```bash
fae validate --json   # JSON-only output, for programmatic parsing
```

## Parts without a complete descriptor (stub-aware)

If `parts.<designator>` references a `part: lcsc:...` without a descriptor in `library/parts/`,
or a descriptor whose `class`/`pinout` is still unfilled, `validate` **does not block** — it
emits `W_PART_NOT_IN_LIBRARY` as a warning. Use `fae catalog fetch <lcsc_id>` to generate the
stub, fill in `class`/`pinout` from the datasheet (see `datasheet-extraction.md`), then validate
again.

## Placement: candidates, not a single answer

`fae place` generates up to 3 candidates (heuristics `compact`, `spread`, `thermal_first`),
ordered by cost. None is "the right one" — review the SVGs in `build/candidate_*.svg`, pick one,
and use `--heuristic <name>` in `render`/`emit` to work with it specifically. Warnings on a
candidate (overlap, out of outline, `max_distance_mm` violation) don't block, but should be
brought to the user before proceeding to `emit`.

## Before trusting `emit`/`routecheck` for fabrication

Output is only dimensionally reliable for parts with **real package geometry** (`ref` to a
`component_package` with a footprint, from a datasheet or from `catalog fetch`). Parts without
this appear in `EmitReport.degradations` with `code: NO_REAL_FOOTPRINT` — report this to the user
explicitly, don't present the output as fabrication-ready without that caveat.

## Recording what you did

After any non-obvious decision (a placement heuristic you chose, an estimated value in the
absence of data, a field marked as uncertain), run:

```bash
fae audit note --actor llm --summary "short description of the decision and why"
```

See `audit.md` for the full vocabulary.
