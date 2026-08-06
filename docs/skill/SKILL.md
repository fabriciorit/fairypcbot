---
name: fairypcbot
description: Design printed circuit boards from text using the fairypcbot framework (`fae` CLI) — author intent.yaml constraints, validate, elaborate the netlist, place, and emit files importable into EasyEDA Pro or any Specctra-capable CAD tool. Use whenever the user asks to create, modify, validate, place, route-check or export a PCB/schematic/board with fairypcbot or `fae`, ingest a component datasheet, or fetch an LCSC part.
license: Apache-2.0
compatibility: Model-agnostic (Claude, Gemini, GPT, or any LLM with shell access).
canonical_source: "fae skill"   # this file ships inside the package; the CLI renders it resolved
---

# fairypcbot

## What this is

A text-driven PCB construction framework. Roles are strict and must not be blurred:

- **You (the LLM) are the constraint author.** You write YAML: `parts`, `nets`, `intents`,
  `placement_hints`.
- **The framework materializes.** It validates, derives the netlist, computes coordinates,
  renders and emits CAD files.
- **The user arbitrates.** They review errors, choose among placement candidates, confirm data
  extracted from datasheets.

**You never write coordinates and never hand-edit geometry.** If you catch yourself computing an
x/y for a part, you are working around the framework instead of using it — express the goal as a
`placement_hint` or an `intent` instead.

## Preflight (do this before the first action, every session)

```bash
fae version --json  # which build you are driving (see below) — do this first
fae --help          # confirm the CLI is installed and see the command surface
fae llm             # the canonical index for LLMs — authoritative over this file
fae llm workflow    # the pipeline and the correction loop
```

If `fae` is not found, the project is a Python package (`requires-python >=3.11`); install it in
the environment the user points you at (`pip install fairypcbot`, or `pip install -e ".[dev]"`
from a checkout) — ask before creating or mutating environments.

### Which fairypcbot this is

<!-- fae:identity -->

That block is resolved by `fae skill` at read time, from the installation that produced it — it is
not a stamp and cannot go stale. A commit identifies one tree exactly; a version string is a label
two different trees can share, so prefer the commit whenever it is present.

Get the same data machine-readably at any time:

```bash
fae version --json     # structured: version, commit, branch, dirty, tag, commit_source
fae version            # one line, human readable
```

Act on `commit_source`: `git` means it was read from a live checkout (authoritative, and `dirty`
tells you whether uncommitted edits make even the hash incomplete); `build_stamp` means it was
recorded when the wheel was built; `unknown` means a plain install with no checkout — the commit
was never packaged and is genuinely unknowable, so fall back to the version and say so if the
distinction matters.

**If you are reading this file directly from the repository rather than via `fae skill`**, the
identity block above is an unresolved marker. Run `fae version --json` to fill the gap, and note
that the file on disk may describe a tree other than the one installed.

**This file is a map, not the source of truth.** `fae llm <topic>` ships with the installed
version and always wins over anything written here; the actual behavior of a command wins over
both. If you find a discrepancy, tell the user — do not assume the docs are right.

## The pipeline

```
intent.yaml → validate → elaborate → place → render → emit → routecheck
```

| Command | Produces | Notes |
|---|---|---|
| `fae init <project>` | skeleton: `intent.yaml`, `blocks/`, `build/`, `audit/` | start here for a new board |
| `fae validate [--json]` | structured `{path, code, message, suggestion}` items | reports **all** issues at once |
| `fae elaborate` | `build/netlist.json`, `build/rules.json` + electrical linter | aborts if validate failed |
| `fae place [--json] [--no-svg]` | `build/placement.json` + `build/candidate_*.svg` | up to 3 candidates |
| `fae render --heuristic <name> [--ratsnest]` | re-renders an existing candidate's SVG | no re-placement |
| `fae emit --target easyeda_pro\|easyeda_std\|specctra [--heuristic <n>]` | CAD-importable file | requires `place` |
| `fae routecheck [--jar <path>]` | headless Freerouting over the DSN | missing Freerouting = skip, not an error |

Supporting commands: `fae schema <name>` (JSON Schema of `intent`, `component_class`,
`component_part`, `component_package`, `datasheet_extract`, `audit_event`), `fae catalog fetch
<lcsc_id>`, `fae datasheet ingest|review`, `fae audit note|show|trace`, `fae layout import`.

Every command is independent and re-runnable; there is no hidden state beyond `build/` and
`audit/`.

## Authoring `intent.yaml`

Read `fae llm intent-authoring` before writing or editing one. The shape:

```yaml
fairypcbot: "0.1"
kind: board                 # or "block" for a reusable block (omits the `board` section)
name: my_project
description: >
  What this board does, in 1-3 sentences.

board:
  layers: 2
  # outline is OPTIONAL — omit it unless a real enclosure/slot fixes the geometry.
  # The placer derives the smallest viable board on its own.

parts:
  U1: {part: "lcsc:C77964"}   # `part:` (real catalog instance) XOR `class:` (behavior only)

nets:
  V3V3: [U1.vdd, C1.p1]       # designator.LOGICAL_ROLE — never a physical pin number

intents:
  - {type: power_rail, net: V3V3, voltage_v: 3.3, max_current_a: 0.5}

placement_hints:
  - {part: U1, region_pref: center}
```

Non-negotiables:

- `nets` reference **roles** (`vdd`, `gnd`, `swdio`) declared in the class, never chip pin
  numbers. The role→pin mapping lives in `pinout:` of the part descriptor.
- `part:` and `class:` are mutually exclusive on the same designator.
- `mounting_holes` with explicit coordinates require an explicit `outline`.
- Intent types to start from: `power_rail`, `diff_pair`, `decouples`, `high_current`,
  `analog_sensitive`. Run `fae schema intent` for the exact fields — don't recall them.
- Reusable blocks come in via `imports: [{path: blocks/power_supply}]`; block designators share
  the root namespace, so collisions are hard errors.

## Working the correction loop

`validate` and `elaborate` return every problem at once. **Fix all of them, then re-run** — do not
fix one item and re-run repeatedly.

Read the `suggestion` field; it is the intended fix path. `code` is stable across versions and is
safe to branch on programmatically (e.g. `W_PART_NOT_IN_LIBRARY` → `fae catalog fetch`). Use
`fae llm errors` for the code catalogue.

Severity: errors block (non-zero exit). Warnings do not block but must never be silently swallowed
— summarize them for the user and ask whether to proceed or fix first.

## Placement: candidates, not an answer

`fae place` emits up to 3 candidates (`compact`, `spread`, `thermal_first`) ordered by cost. The
lowest cost is not automatically correct. Review `build/candidate_*.svg`, present the trade-off to
the user, and pass `--heuristic <name>` to `render`/`emit` to commit to one. Candidate warnings
(overlap, outside outline, `max_distance_mm` violated) do not block but belong in front of the
user before `emit`.

## Never present output as fabrication-ready without checking degradations

`fae emit` returns an `EmitReport`. Parts lacking real package geometry appear in
`degradations` with `code: NO_REAL_FOOTPRINT` — for those, the output is a placement preview, not
routable or manufacturable. **Always relay this to the user explicitly.** Only parts whose
`component_package` carries a real footprint (from a datasheet or `catalog fetch`) are
dimensionally trustworthy.

## Data integrity rules (these override convenience, always)

1. **Never fabricate data.** A field without a reliable source stays absent/`null` with
   `provenance: {source: missing}`. A plausible-looking invented value is the worst possible
   outcome in this framework.
2. **Precedence: `datasheet` > `easyeda_api`/web > estimate.** Never overwrite a value whose
   `provenance.source` is `datasheet` or `user`. If a package variant needs different geometry,
   add a sibling variant and flag the conflict — never replace silently.
3. **Never mark something `extracted` you did not reread and judge plausible**, and never touch an
   item already `verified_by: user` unless the user asks.

## Library objects

Four kinds under `library/`: `component_class` (`classes/`, electrical vocabulary — pin roles,
required params, linear `extends`), `component_part` (`parts/`, real MPN + `pinout` +
`package.ref` + `datasheet_ref`, id `lcsc:CXXXXX`), `component_package` (`packages/`, a **family**
with named **variants** — "SOIC-8" is not one geometry), `datasheet_extract` (`datasheets/`).

`fae catalog fetch <lcsc_id>` generates a *stub* part; you fill `class`/`pinout` **from the
datasheet**, not from memory. Check for an existing reusable class/package before creating a new
one. Details: `fae llm library`.

## Datasheets: differentiated effort

`fae datasheet ingest <pdf> --part lcsc:CXXXX --source-url <public URL>` hashes the PDF, dumps
per-page text to `build/datasheet_text/` (so you can read it without vision), and writes a
checklist skeleton. **Always pass `--source-url` when the PDF came from the web** — a scratchpad
or `/tmp` path recorded as the origin is a silent traceability trap.

- **High effort** (pinout, absolute maximum, operating conditions, electrical, identification):
  iterate. If a value looks implausible, reread the page. Still unsure → `extraction_status:
  needs_user` with `notes` naming exactly what is uncertain. Use the class's canonical param name
  (`rds_on_ohm`), not the datasheet's literal wording.
- **Best-effort** (curves, waveforms, complex state machines): always capture the reference (title,
  axes+units, page). Digitizing points is optional, `approximate: true`, and after ~2 poor attempts
  **stop** and mark `gave_up` with the reason. That is the expected outcome, not a failure.
- Always attempt `document_version`; mark it `read`, `unreadable`, or `absent` — never leave it
  blank silently.
- Never record a number without `source: {page, section}`.

Then `fae validate` and `fae datasheet review` (the user confirms → `verified_by: user`). Full
procedure: `fae llm datasheet-extraction`.

## Audit trail

Commands log themselves automatically. What you log manually are decisions the framework cannot
infer: a heuristic chosen for a stated reason, a value estimated in the absence of data, an
ambiguity in `intent.yaml` resolved one way among several, an item you gave up on.

```bash
fae audit note --actor llm --summary "why this decision, in one sentence"
fae audit show [--phase <stage>] [--actor llm]
fae audit trace build/placement.json
```

Treat this as part of the work: it is how the next session answers "why is this board like this?".
See `fae llm audit`.

## Common tasks → entry point

| The user wants | Do this |
|---|---|
| A new board from a description | `fae init` → write `intent.yaml` (`fae llm intent-authoring`) → validate loop |
| To add a real part | `fae catalog fetch <lcsc>` → fill `class`/`pinout` from the datasheet → validate |
| To know why validation fails | Read `suggestion` on each item; `fae llm errors` for the code |
| A board to export to CAD | `place` → show candidates → `emit --target easyeda_pro --heuristic <n>` → report degradations |
| To check routability | `fae routecheck` (gracefully absent if Freerouting isn't installed) |
| To reabsorb manual CAD edits | `fae layout import` |
| Deeper internals | `spec.md`, `docs/ir.md`, `docs/easyeda_format.md`, `docs/library_repo.md`, `docs/limitations.md` |

## Anti-patterns

- Computing or hand-editing coordinates, footprints, or emitted CAD files.
- Inventing a pinout, a package dimension, or an electrical parameter "to move forward".
- Re-running `validate` after each single fix instead of fixing the whole batch.
- Presenting an `emit` result as fabrication-ready while `NO_REAL_FOOTPRINT` degradations exist.
- Picking the lowest-cost placement candidate silently instead of putting the choice to the user.
- Silently dropping warnings from the report you give the user.
- Reciting optional field names from memory instead of running `fae schema <name>`.
