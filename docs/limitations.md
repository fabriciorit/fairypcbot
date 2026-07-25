# Known limitations

This page lists limitations that are current, deliberate, or simply not yet closed — as opposed to
bugs. It exists so that anyone operating fairypcbot (human or LLM) knows what to expect before
trusting an output for fabrication, or before extending a subsystem.

## Placement

- **Domains are flat, not hierarchical.** A domain (`place/domains.py`) is a flat set of
  designators, with no subdomain tree. Nothing in the current pipeline instantiates a genuinely
  hierarchical domain (e.g. a "power supply" domain containing its own "buck" subdomain with
  internal parts) — see the application-circuit-expansion limitation below.
- **Floorplan uses a coarse grid, not slicing-tree/simulated annealing.** The outline is split
  into a `cols × rows` grid (roughly `sqrt(N domains)`), each cell is classified into a region
  (north/south/east/west/center), and domains are assigned to cells by a deterministic greedy
  algorithm. The three registered heuristics (`compact`, `spread`, `thermal_first`) vary the
  assignment order and cell-selection criterion, not the grid mechanism itself. This trades
  refinement quality for determinism (needed by automated tests) and avoids the complexity of a
  full annealing optimizer.
- **Non-rectangular outlines fall back to a coarse bounding box.** Exact dimension calculation is
  only implemented for `rect` and `circle` outlines; `polygon`/`dxf_ref` shapes fall back to a
  crude 40×40mm approximation. Grid-cell-inside-outline logic assumes a rectangular bounding box.
- **Package size is a name-based approximation, not real footprint data**, unless real geometry
  was obtained via `catalog fetch` (see the emit/footprint limitation below). The fallback is a
  substring-to-dimension lookup table, useful for giving the placer a size hint, not for
  fabrication-grade sizing.
- **Legalization is non-blocking.** Overlap, out-of-outline, and mounting-hole-clearance
  violations are reported as warnings on a placement candidate, never used to discard the
  candidate outright. Candidate rejection is reserved for downstream routability feedback.

## Routability estimate

- **The routability estimate is heuristic, not a real routing pass.** It compares an estimated
  wiring demand (half-perimeter wirelength per net, with a fanout correction for nets with more
  than two members) against an estimated channel supply (outline area × layers × a fixed
  utilization factor), without ever invoking a router. It does not model detours around parts or
  vias, nor real design-rule checks.
- **The acceptance threshold is empirically calibrated, not analytically derived, and known to be
  optimistic near the boundary.** Calibration against real-world routing outcomes showed that a
  layout accepted at a ratio close to the original threshold (~0.93) still failed to route
  completely in practice, while a much looser layout (~0.42) routed at 100%. The threshold was
  tightened accordingly, but it remains a single empirical data point, not a proven bound — treat
  any accepted candidate near the threshold with caution and prefer running the actual routability
  oracle (`fae routecheck`) before trusting the result.
- **`RoutecheckResult` does not report route-completion coverage.** It only reports whether the
  Freerouting process ran and produced a session file, not what fraction of nets were actually
  routed. A parser for that metric is not yet implemented.

## Emit / footprint geometry

- **Footprint geometry from `catalog fetch` is best-effort.** The EasyEDA footprint parser is
  built from the publicly documented shape-line format; it degrades gracefully to
  `footprint: null` / `provenance.footprint: missing` when parsing fails or when a component
  requires a second API call to resolve a separate footprint UUID (not yet implemented) — it never
  fabricates geometry.
- **Without real pad geometry, `emit` output is a placement preview, not a fabricable board.**
  Parts lacking real footprint geometry appear in `EmitReport.degradations` with
  `code: NO_REAL_FOOTPRINT`; both the EasyEDA Std and Specctra DSN emitters produce only a
  silhouette/placeholder pin layout for those parts — this is reported per part on every `emit`
  run and should always be surfaced to the user before treating output as fabrication-ready.
- **EasyEDA Std emitter confidence is format-level medium, not fully validated.** The shape-line
  encoding and the document envelope for footprint/symbol documents are confirmed against real
  API responses; the `head.docType` value used for a complete PCB document remains an assumption
  (only isolated footprint and symbol document samples have been observed).
- **Specctra DSN emitter follows a public, stable specification**, giving it higher structural
  confidence than the EasyEDA Std emitter, but geometry quality still depends on the footprint
  limitation above.
- **EasyEDA Pro (`.eprj2`) support is partial.** Component, attribute, and pad/net records are
  supported; through-hole pads and full board-outline representation are not yet confirmed against
  real documents. Only the same shape-line vocabulary used for footprints is interpreted for
  symbols (see below); silkscreen, copper pour, and solder-mask layers are not read or written at
  all.
- **Schematic symbol interpretation covers a limited primitive set.** Pins, open polylines, closed
  paths built only from `M`/`L`/`Z` commands, and body rectangles are supported; ellipses, arcs,
  and free text are not.
- **The generated schematic sheet is best-effort, not a finished schematic.** Net labels are used
  in place of native ports, polygon closure is not guaranteed, and layout does not cluster related
  parts — it is meant as a starting point for manual cleanup, not a publish-ready schematic.
- **The Freerouting invocation convention is unverified against a real run in this repository's
  CI/test environment** (no Java/Freerouting jar assumed available) — the command-line flags
  follow the publicly documented convention for headless execution but have not been exercised
  end-to-end here.

## Validation

- **`part:` references without a library descriptor are a warning, not an error.** If
  `parts.<designator>` references a `part: lcsc:...` with no descriptor in `library/parts/`, or a
  descriptor whose `class`/`pinout` is incomplete, `validate` emits `W_PART_NOT_IN_LIBRARY` and
  continues. This means a project can "validate clean" while still containing parts whose catalog
  data hasn't been resolved — by design, since stage-2 validation targets structural/referential
  errors, not catalog completeness.
- **`component_class.extends` supports only single, linear inheritance.** Multiple inheritance
  (diamond composition of two base classes) is not supported or resolved — it is rejected by
  design. Richer composition between classes must be modeled as explicit independent fields in the
  YAML, not through `extends`.
- **`elaborate` does not expand `application_circuit` into instantiated designators.** A class
  that declares an `application_circuit` (e.g. a buck converter listing its inductor and
  capacitors) is not automatically expanded into concrete parts, nets, and sizing values during
  elaboration — auxiliary parts (decoupling capacitors, crystal load caps, etc.) must currently be
  declared explicitly in `intent.yaml`. The sizing functions and templates exist and are unit
  tested in isolation, but the orchestration step that would instantiate, wire, and size them
  automatically is not implemented. This is also why domains stay flat (see above): nothing yet
  produces a genuinely hierarchical application-circuit domain.

## Type checking

- **`mypy --strict` covers only `schemas` and `registry`.** The rest of the codebase (CLI,
  `validate/`, `audit/`, etc.) uses normal (non-strict) type checking. This is a deliberate
  narrowing of scope: modules such as the CLI depend on third-party decorators whose stubs don't
  always satisfy strict mode without disproportionate effort relative to the value delivered.
