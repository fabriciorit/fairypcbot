"""Reading/querying the audit trail (`fairypcbot audit show/trace`)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from fairypcbot.audit.hashing import sha256_file
from fairypcbot.schemas.audit import AuditEvent


def iter_events(
    project_root: Path,
    run: str | None = None,
    phase: str | None = None,
    actor: str | None = None,
) -> Iterator[AuditEvent]:
    audit_dir = Path(project_root) / "audit"
    if not audit_dir.is_dir():
        return
    for jsonl_path in sorted(audit_dir.glob("*.jsonl")):
        if run and not jsonl_path.name.startswith(run):
            continue
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = AuditEvent.model_validate(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue  # corrupted line: tolerated, skipped
                if phase and ev.phase != phase:
                    continue
                if actor and ev.actor != actor:
                    continue
                yield ev


def build_trace(project_root: Path, artifact_path: str) -> list[AuditEvent]:
    """Simplified provenance reconstruction (see the documentation): direct search by path/hash.

    Does not chain multiple hops between intermediate artifacts (netlist.json -> placement.json
    etc.) because M1 does not generate those artifacts yet; full chain reconstruction gets richer
    from M2+ onward.
    """
    target = Path(project_root) / artifact_path
    current_hash = sha256_file(target) if target.exists() else None

    matches: list[AuditEvent] = []
    for ev in iter_events(project_root):
        refs = [*ev.inputs, *ev.outputs]
        for ref in refs:
            if ref.path == artifact_path or ref.path == str(target):
                matches.append(ev)
                break
            if current_hash and ref.sha256 == current_hash:
                matches.append(ev)
                break
    return matches
