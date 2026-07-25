# fairypcbot — index for LLMs

Documented version: **0.1.0** (must match `fairypcbot.__version__` — checked in CI).

This is the entry point for any LLM operating fairypcbot on behalf of a user. Read this first;
open the topics below only when the task requires it (progressive disclosure — don't load
everything at once).

**Access**: `fae llm` prints this index; `fae llm <topic>` prints a topic (works from any pip
installation, no dependency on having the repository path).

**Size contract** (enforced by `tests/docs/test_llm_docs_contract.py`): this index has at most
150 lines; each topic below has at most 400 lines. If a topic grows beyond that, it must be
split — never read "halfway" due to budget overflow.

## What fairypcbot is

A text-driven PCB construction framework. You (the LLM) are the **constraint author** in YAML
(`intent.yaml`); the framework **validates and materializes** those constraints into geometry;
the user **arbitrates** (reviews errors, approves placements, confirms data extracted from
datasheets). You never manipulate coordinates directly — you only write `intents`, `nets`,
`placement_hints`.

## Topics

| Topic | When to read | Command |
|---|---|---|
| [`workflow.md`](workflow.md) | Always, before the first action on a project | `fae llm workflow` |
| [`intent-authoring.md`](intent-authoring.md) | When writing/editing `intent.yaml` | `fae llm intent-authoring` |
| [`library.md`](library.md) | When creating/referencing classes, parts, packages | `fae llm library` |
| [`datasheet-extraction.md`](datasheet-extraction.md) | When running `fae datasheet ingest` | `fae llm datasheet-extraction` |
| [`errors.md`](errors.md) | When interpreting an error/warning `code` | `fae llm errors` |
| [`audit.md`](audit.md) | When deciding whether/how to log a decision | `fae llm audit` |

## Rules that apply across every topic

1. **Never fabricate data.** A field without a reliable source stays absent/`null` with
   `provenance: {source: missing}` — not a plausible-looking value.
2. **The datasheet is the canonical reference**, always (in the published version). API/web data
   is convenience only. Never overwrite a value whose `provenance.source` is `datasheet` or `user`.
3. **Every error has a stable `code` plus an actionable `suggestion`.** Use `suggestion` to fix
   the issue — don't guess from `message` alone.
4. **`fae schema <name>`** prints the JSON Schema of any model (`intent`, `component_class`,
   `component_part`, `component_package`, `datasheet_extract`, `audit_event`) — use it before
   generating YAML of a kind whose exact shape you're unsure of.
5. **Log non-trivial decisions** via `fae audit note --actor llm` (see `audit.md`) — a chosen
   heuristic, an estimated value, data marked uncertain.
6. If anything in this index conflicts with the actual behavior of a command, the actual behavior
   wins — report the discrepancy to the user, don't assume the doc is correct.

## Where else to look (outside `docs/llm/`)

- `spec.md` — full project specification (longer, not designed for context budget).
- `docs/ir.md`, `docs/easyeda_format.md`, `docs/library_repo.md` — technical depth beyond what's
  needed for everyday use.
- `docs/limitations.md` — known limitations by area (placement, emit, validation, type-checking).
