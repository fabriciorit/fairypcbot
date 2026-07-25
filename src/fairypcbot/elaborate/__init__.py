"""Stage 3 (`fairypcbot elaborate`): netlist.json + rules.json + electrical linter (spec section 4).

Note (see the documentation): this stage does NOT expand `application_circuit` into instantiated designators —
the spec does not define a pin-to-pin wiring convention for templates (section 3.4), so that
expansion is left for a future milestone, once that convention is designed. `elaborate` here
resolves only what is already explicit in `intent.yaml`.
"""
