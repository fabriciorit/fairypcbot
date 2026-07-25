"""Registry of component modeling/sizing functions.

Each function returns `(value, justification)` — the justification text is what feeds the audit
trail (spec section 8.2: "every non-deterministic choice... generates a `decision` event with a
readable `reason`"). The caller is responsible for logging the event; this module only computes.

`is_model_implemented` lets validation (M1) and elaboration (M3) check whether a name referenced
in `ComponentClass.models` or `ApplicationCircuitPart.sizing` is actually implemented — if not, the
corresponding check emits `W_MODEL_NOT_IMPLEMENTED` (warning), since not every base class needs a
ready sizing model at this milestone.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_MODELS: dict[str, Callable[..., tuple[Any, str]]] = {}


def component_model(name: str) -> Callable[[Callable[..., tuple[Any, str]]], Callable[..., tuple[Any, str]]]:
    def deco(fn: Callable[..., tuple[Any, str]]) -> Callable[..., tuple[Any, str]]:
        _MODELS[name] = fn
        return fn

    return deco


def is_model_implemented(name: str) -> bool:
    return name in _MODELS


def known_models() -> list[str]:
    return sorted(_MODELS.keys())


def call_model(name: str, **kwargs: Any) -> tuple[Any, str]:
    return _MODELS[name](**kwargs)


def get_model(name: str) -> Callable[..., tuple[Any, str]] | None:
    return _MODELS.get(name)


@component_model("buck.inductor_sizing")
def buck_inductor_sizing(
    vin_v: float,
    vout_v: float,
    iout_max_a: float,
    f_sw_hz: float = 500_000.0,
    ripple_ratio: float = 0.3,
) -> tuple[float, str]:
    """Inductance for a buck converter in continuous conduction mode (classic formula)."""
    ripple_current_a = iout_max_a * ripple_ratio
    inductance_h = (vin_v - vout_v) * (vout_v / vin_v) / (f_sw_hz * ripple_current_a)
    justification = (
        f"L = (Vin-Vout)×(Vout/Vin)/(f_sw×ΔIL) with ΔIL={ripple_ratio*100:.0f}% of Iout "
        f"({iout_max_a:.2f}A) at f_sw={f_sw_hz/1e3:.0f}kHz — classic buck sizing in continuous "
        f"conduction mode"
    )
    return inductance_h, justification


@component_model("buck.cin_sizing")
def buck_cin_sizing(
    iout_max_a: float, f_sw_hz: float = 500_000.0, vripple_v: float = 0.1
) -> tuple[float, str]:
    """Input capacitance to limit the voltage ripple on Cin (usual approximation)."""
    capacitance_f = iout_max_a / (4 * f_sw_hz * vripple_v)
    justification = (
        f"Cin = Iout/(4×f_sw×ΔVripple) for ΔVripple={vripple_v*1e3:.0f}mV at "
        f"f_sw={f_sw_hz/1e3:.0f}kHz — usual approximation for a buck input capacitor"
    )
    return capacitance_f, justification


@component_model("buck.cout_sizing")
def buck_cout_sizing(
    ripple_current_a: float, f_sw_hz: float = 500_000.0, vripple_v: float = 0.05
) -> tuple[float, str]:
    """Output capacitance to limit the voltage ripple on Cout (usual approximation)."""
    capacitance_f = ripple_current_a / (8 * f_sw_hz * vripple_v)
    justification = (
        f"Cout = ΔIL/(8×f_sw×ΔVripple) for ΔVripple={vripple_v*1e3:.0f}mV at "
        f"f_sw={f_sw_hz/1e3:.0f}kHz — usual approximation for a buck output capacitor"
    )
    return capacitance_f, justification


@component_model("ldo.cin_cout_sizing")
def ldo_cin_cout_sizing(min_capacitance_f: float = 1e-6) -> tuple[float, str]:
    justification = (
        f"{min_capacitance_f*1e6:.1f}µF ceramic — typical minimum value recommended by generic "
        f"LDO datasheets to guarantee loop stability"
    )
    return min_capacitance_f, justification


@component_model("mcu.decoupling_sizing")
def mcu_decoupling_sizing(capacitance_f: float = 100e-9) -> tuple[float, str]:
    justification = (
        f"{capacitance_f*1e9:.0f}nF per power pin — standard decoupling practice for digital "
        f"MCUs"
    )
    return capacitance_f, justification


@component_model("crystal.load_cap_sizing")
def crystal_load_cap_sizing(
    load_capacitance_f: float = 18e-12, stray_capacitance_f: float = 3e-12
) -> tuple[float, str]:
    capacitance_f = 2 * (load_capacitance_f - stray_capacitance_f)
    justification = (
        f"C = 2×(CL−Cstray) = 2×({load_capacitance_f*1e12:.1f}pF−{stray_capacitance_f*1e12:.1f}pF) "
        f"— standard formula for crystal load capacitors"
    )
    return capacitance_f, justification
