"""`fairypcbot routecheck` — routability oracle via headless Freerouting (spec section 6.4/10.6).

Freerouting is an **optional** external dependency (Java), detected at runtime (spec 10.6) — the
absence of `java` or the `.jar` is not an error, it is a result ("did not run, here is how to
install it").

**Confidence (see the documentation)**: the CLI flags used below (`-de`/`-do`) follow the convention publicly
documented by Freerouting for headless execution, but they have not been tested in this
environment (no Java/jar available to validate). Treat this as best-effort — if the Freerouting
version in use has a different CLI, adjust `FREEROUTING_CLI_ARGS` based on the jar's actual
`--help` output.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RoutecheckResult:
    ran: bool
    success: bool
    message: str
    output_path: Path | None = None
    stdout: str = ""
    stderr: str = ""


def find_java() -> str | None:
    return shutil.which("java")


def find_freerouting_jar(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    env_path = os.environ.get("FAIRYPCBOT_FREEROUTING_JAR")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    return None


def run_routecheck(
    dsn_path: Path,
    outdir: Path,
    *,
    jar_path: Path | None = None,
    timeout: float = 300.0,
    runner: Callable[..., Any] = subprocess.run,
) -> RoutecheckResult:
    java = find_java()
    jar = find_freerouting_jar(jar_path)
    if java is None or jar is None:
        missing = []
        if java is None:
            missing.append("java (not found on PATH)")
        if jar is None:
            missing.append("the Freerouting .jar (pass --jar or set FAIRYPCBOT_FREEROUTING_JAR)")
        return RoutecheckResult(
            ran=False,
            success=False,
            message="Freerouting not detected — routecheck skipped. Missing: " + "; ".join(missing),
        )

    outdir.mkdir(parents=True, exist_ok=True)
    ses_path = outdir / "board.ses"
    cmd = [java, "-jar", str(jar), "-de", str(dsn_path), "-do", str(ses_path), "-mp", "1"]

    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RoutecheckResult(ran=False, success=False, message=f"Failed to run Freerouting: {exc}")

    ok = proc.returncode == 0 and ses_path.exists()
    message = (
        ("Freerouting ran; see " if ok else f"Freerouting returned code {proc.returncode}; see ")
        + "build/board.ses and stdout/stderr below. Automatic parsing of \"100% routed\" "
        "is not implemented in this version (see the documentation) — inspect the output manually."
    )
    return RoutecheckResult(
        ran=True,
        success=ok,
        message=message,
        output_path=ses_path if ok else None,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
