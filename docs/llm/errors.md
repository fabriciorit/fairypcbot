# Interpreting errors and warnings

Every error/warning item has the same shape: `{path, code, message, suggestion}`. **Use
`suggestion` to fix it** — no need to guess from `message` alone. `code` is stable across
versions; it can be used for programmatic logic (e.g. "if `W_PART_NOT_IN_LIBRARY`, run catalog
fetch").

Full catalog in `fairypcbot.schemas.error_codes.ErrorCode` — the list below is a quick map by
area, not exhaustive.

## Stage 2 — `validate`

| Prefix/code | Meaning | Typical action |
|---|---|---|
| `E_YAML_SYNTAX`, `E_SCHEMA_*` | Malformed YAML or outside the schema | Fix the syntax/structure; `fae schema intent` for the exact schema |
| `E_UNKNOWN_*_REF`, `E_UNKNOWN_PIN` | Reference to something that doesn't exist | Check the designator/net/role name |
| `E_IMPORT_CYCLE`, `E_IMPORT_NOT_FOUND` | Problem in `imports:` | Fix the path or remove the circular dependency |
| `E_DUPLICATE_DESIGNATOR` | Two designators collide (root + imported block) | Rename one of the two |
| `E_INTENT_UNKNOWN_TYPE` | Intent `type` not registered | See valid types in `intent-authoring.md` |
| `W_PART_NOT_IN_LIBRARY` | `part:` without a descriptor (or incomplete stub) | `fae catalog fetch <lcsc_id>`, then complete it from the datasheet |
| `W_MODEL_NOT_IMPLEMENTED` | Class `models:` references an unregistered function | Doesn't block; informational |
| `E_DATASHEET_NOT_FOUND` | `datasheet_ref` points to a nonexistent file | `fae datasheet ingest` or fix the reference |
| `W_DATASHEET_INCOMPLETE` | Datasheet doesn't cover all of the class's `params.required` | Extract the missing parameters (see `datasheet-extraction.md`) |
| `W_DATASHEET_VERSION_UNKNOWN` | Document version not confirmed | Reread the PDF cover/footer; or mark `document_version_status: absent` |
| `W_PACKAGE_REF_NOT_FOUND` | `package.ref` points to a nonexistent family/variant | Create the package or fix the reference |

## Stage 3 — `elaborate` (electrical linter)

| Code | Meaning |
|---|---|
| `E_POWER_TREE_UNREACHABLE` | Floating vdd/vcc pin, or a power net doesn't reach any `power_rail` |
| `W_CURRENT_OVER_TRACE_CAPACITY` | High-current net may need a wider trace than the default (simplified IPC-2152 approximation) |
| `W_LOGIC_LEVEL_MISMATCH` | Two parts on the same net with non-overlapping voltage ranges |
| `W_FLOATING_REQUIRED_PIN` | EN/VREF/thermal-pad pin not connected to any net |
| `W_MISSING_DECOUPLING` | IC power pin without a corresponding `decouples` intent |

## Stage 5 — `emit`

`EmitReport.degradations` (not the same list as validate — comes per part, in the `fae emit`
report): `code: NO_REAL_FOOTPRINT` means the part has no real package geometry — the output for it
is just a placement preview, not routable/fabricable. Report this to the user whenever it appears,
don't omit it.

## Severity

`errors` block (the command exits with a non-zero code). `warnings` don't block, but should never
be silently ignored — summarize them for the user and ask whether to proceed as-is or fix them
first.
