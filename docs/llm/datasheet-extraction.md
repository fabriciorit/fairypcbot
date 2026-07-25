# Datasheet extraction

The datasheet is the project's canonical reference (in the published version) — API/web data is
convenience, never authority. This is the most labor-intensive task you perform in fairypcbot;
read this in full before starting.

## Workflow

```bash
fae datasheet ingest <path_to_pdf> --part lcsc:CXXXX --source-url <manufacturer_public_url>
```

**Always pass `--source-url` when the PDF came from a public URL** (the common case — you
downloaded it from a manufacturer/distributor site). Without it, the local file path becomes the
recorded origin in `source_pdf.path_or_url` — and a path under `/tmp/` or a session scratchpad
does not survive after the session ends, breaking the traceability that the rest of the
provenance system depends on. As a rule, a local-only path recorded without `--source-url` is a
silent trap: it looks like a valid reference until someone tries to follow it later and finds
nothing there. Only omit `--source-url` when the document genuinely has no public URL
(confidential, received by email) — and in that case, consider recording the real origin (from
whom, how) in `notes` on some item, since `path_or_url` alone won't tell that story.

The command: hashes the PDF (sha256 of the raw bytes), extracts per-page text to
`build/datasheet_text/<id>/page_NNN.txt` (so you can read it without needing vision over the PDF),
and creates a YAML skeleton at `library/datasheets/<id>.yaml` with a checklist derived from the
class (its `params.required`), marked `extraction_status: needs_user`.

You fill in the skeleton by reading the extracted text (and the PDF directly when you need a
table/chart the text didn't capture well). Then:

```bash
fae validate           # checks structure + basic coverage of required params
fae datasheet review   # user confirms the extracted items (becomes verified_by: user)
```

## Document version — not optional to attempt

Every formal datasheet declares a revision (cover page or footer: "Rev. 3", "Doc ID: ...",
publication date). Always look for it. Fill in `document_version` and mark:
- `document_version_status: "read"` — you found it and are confident in the reading.
- `document_version_status: "unreadable"` — you tried, couldn't read it with confidence.
- `document_version_status: "absent"` — the document genuinely doesn't declare a version (rare;
  it's information about the manufacturer document's quality, record it without blame).

Never leave it blank silently — absence of an attempt is not the same as absence of a version.

## Effort policy — DIFFERENTIATED by section

This is the most important part of this document.

### High effort — iterate until resolved or escalate to the user

**Pinout, electrical characteristics (`absolute_maximum`, `operating_conditions`, `electrical`),
identification.** These are tabular data, usually well extractable from the text. For each item:

1. Try to extract it from the page text.
2. If the result looks incoherent or implausible (wrong unit, value out of a reasonable order of
   magnitude, symbol that doesn't match anything known), **reread the page, try again** — don't
   accept the first result if it doesn't make sense.
3. If after trying you're still not confident, mark `extraction_status: "needs_user"` with a
   `notes` explaining exactly what's uncertain ("table on page 4 has a column whose header I
   couldn't read clearly") — this is the trigger for `fae datasheet review` to ask the user
   specifically about that item.
4. **`param`, when applicable, must be the class's canonical parameter name** (e.g. `rds_on_ohm`,
   not "Rds(on)" or a literal translation of the datasheet term) — this is what lets `validate`
   automatically check coverage against the class's `params.required`.

### Best-effort — don't push past ~2 bad attempts

**Curves/graphs, waveforms, complex state machines.** Always capture the *reference* (title, axes
with unit, page) — that's cheap and always worth doing. Extracting *points* from a curve is
optional:

1. Try once, always with `approximate: true`.
2. If the result is clearly poor (too few points, high uncertainty), try once more at most.
3. After ~2 bad attempts, **stop** — mark `extraction_status: "gave_up"` with a short note of the
   reason. This is not a failure on your part: digitizing a full graph with visual confidence
   (side-by-side reproduction against a crop of the original for the user to confirm) is future
   framework work, not this tool's job today. Reference plus a recorded give-up is the expected
   and acceptable outcome for most cases.

### Application information — worth mapping to the framework's vocabulary

`layout_guidance` (manufacturer placement advice) can be mapped to `intent_type`/`intent_params`
using the same vocabulary as `intent-authoring.md` (e.g. advice like "keep Cin within 2mm of the
VIN pin" becomes `{intent_type: "decouples", intent_params: {max_distance_mm: 2}}`). `formulas`
(sizing formulas) can be compared against functions already registered in
`fairypcbot.registry.models` when the class references them — this is valuable cross-validation,
but it doesn't block if it isn't possible.

## What you never do

- Never fill in a numeric value without `source: {page, section}`.
- Never mark `extraction_status: "extracted"` for something you didn't reread and confirm
  plausible.
- Never overwrite an item already `verified_by: user` without the user explicitly asking for it.
