"""Audit trail writer (spec section 8).

One JSONL file per run: `audit/{run_id}_{phase}.jsonl`. `error` events are always recorded, even
with auditing disabled (`--no-audit` or `audit: false` in the intent) — other event categories are
no-ops when disabled.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fairypcbot.audit.hashing import sha256_file
from fairypcbot.schemas.audit import AuditEvent, FileRef


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S") + "_" + uuid.uuid4().hex[:8]


class AuditWriter:
    def __init__(
        self,
        project_root: Path,
        phase: str,
        run_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.project_root = Path(project_root)
        self.phase = phase
        self.run_id = run_id or new_run_id()
        self.enabled = enabled
        self._path = self.project_root / "audit" / f"{self.run_id}_{self.phase}.jsonl"
        self._file = None

    def _ensure_open(self) -> None:
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a", encoding="utf-8")

    def snapshot_input(self, path: Path) -> FileRef:
        return FileRef(path=str(path), sha256=sha256_file(Path(path)))

    def emit(
        self,
        *,
        actor: str,
        event: str,
        code: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        inputs: list[FileRef] | None = None,
        outputs: list[FileRef] | None = None,
    ) -> None:
        if not self.enabled and event != "error":
            return
        ev = AuditEvent(
            ts=datetime.now(UTC),
            run_id=self.run_id,
            phase=self.phase,  # type: ignore[arg-type]
            actor=actor,  # type: ignore[arg-type]
            event=event,  # type: ignore[arg-type]
            code=code,
            summary=summary,
            detail=detail or {},
            inputs=inputs or [],
            outputs=outputs or [],
        )
        self._ensure_open()
        assert self._file is not None
        self._file.write(ev.model_dump_json() + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> AuditWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
