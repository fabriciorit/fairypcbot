"""Stage 5 (`fairypcbot emit`): materializing the IR into files importable by a target CAD.

Multi-CAD contract in `emit/base.py` (spec section 6.2). No EasyEDA concept may leak
outside `emit/easyeda_std.py` and `catalog/` (spec 10.4) — `emit/specctra_dsn.py` imports
nothing from `emit/easyeda_std.py` nor vice versa; both consume only the neutral IR
(`schemas/ir.py`, `schemas/placement.py`).

See the documentation (best-effort footprint geometry) and the documentation (differing confidence levels between
the DSN format — a stable public spec — and the EasyEDA Std/Freerouting CLI format — reverse
engineered/best-effort, not validated live in this environment).
"""
