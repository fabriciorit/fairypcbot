"""Check 1 (section 4): current budget per net vs. estimated trace capacity.

The minimum trace width is a simplified APPROXIMATION inspired by IPC-2152 (external trace,
10°C temperature rise, 1oz copper) — it does not replace a real thermal analysis, but serves
as an early flag that a high-current net may need a wider trace than the project's assumed
default.
"""

from __future__ import annotations

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.ir import RulesDoc

DEFAULT_TRACE_WIDTH_MM = 0.25  # ~10 mil, common default for signal traces on 2-layer boards


def estimate_min_trace_width_mm(
    current_a: float, temp_rise_c: float = 10.0, copper_oz: float = 1.0
) -> float:
    """Simplified IPC-2152 approximation for an external trace: I = k×ΔT^0.44×(W×H)^0.725."""
    k = 0.048
    width_mil = (current_a / (k * temp_rise_c**0.44)) ** (1 / 0.725) / copper_oz
    return width_mil * 0.0254


def check_current_budget(rules: RulesDoc) -> list[ValidationErrorItem]:
    warnings: list[ValidationErrorItem] = []
    for intent in rules.intents:
        intent_type = getattr(intent, "type", None)
        current_a: float | None = None
        net_name: str | None = None
        if intent_type == "high_current":
            current_a = intent.current_a
            net_name = intent.net
        elif intent_type == "power_rail" and intent.max_current_a is not None:
            current_a = intent.max_current_a
            net_name = intent.net
        if current_a is None or net_name is None:
            continue

        min_width_mm = estimate_min_trace_width_mm(current_a)
        if min_width_mm > DEFAULT_TRACE_WIDTH_MM:
            warnings.append(
                ValidationErrorItem(
                    path=f"nets.{net_name}",
                    code=ErrorCode.W_CURRENT_OVER_TRACE_CAPACITY,
                    message=(
                        f"Net '{net_name}' declares {current_a:.2f}A, above the capacity of the "
                        f"assumed default trace ({DEFAULT_TRACE_WIDTH_MM}mm)"
                    ),
                    suggestion=(
                        f"Use a trace of at least {min_width_mm:.2f}mm for '{net_name}' "
                        f"(simplified IPC-2152 approximation, 1oz/10°C)"
                    ),
                )
            )
    return warnings
