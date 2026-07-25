# Audit trail

Every command (`validate`, `elaborate`, `place`, `emit`, `catalog fetch`, `datasheet ingest`, ...)
already logs events automatically to `audit/*.jsonl` — you don't need to do anything for that to
happen in the normal flow. What you log manually are **decisions the framework has no way of
knowing you made**.

## When to log manually

After any non-deterministic choice you made on the user's behalf:

- You picked a specific placement heuristic for a reason (not just "the lowest-cost one").
- You estimated a numeric value in the absence of reliable data (and why that value).
- You marked a datasheet item `gave_up`/`needs_user` (the reason already lives in the item's
  `notes`, but an audit note helps reconstruct the whole session's context later).
- You resolved an `intent.yaml` ambiguity a specific way among several possible readings.

```bash
fae audit note --actor llm --summary "Chose 'thermal_first' placement because the board has \
  a high-current buck; 'compact' would put it near the noise-sensitive MCU"
```

## Consulting the history

```bash
fae audit show                         # full timeline
fae audit show --phase datasheet       # events from one stage only
fae audit show --actor llm             # only your own notes
fae audit trace build/placement.json   # reconstructs an artifact's provenance (simplified)
```

## Why this matters

The audit trail is what lets the user (or you, in a future session) answer "why did this board end
up this way?" without reconstructing the reasoning from scratch. Treat it as part of the work, not
as optional bureaucracy — especially for decisions that involved uncertainty or estimation.
