# Writing `intent.yaml`

You never write coordinates. You write `parts`, `nets`, `intents` (electrical constraints), and
`placement_hints` (position preferences, not positions). The framework materializes the rest.

## Minimal skeleton

```yaml
fairypcbot: "0.1"
kind: board                 # or "block" for a reusable block (no `board` section)
name: my_project
description: >
  What this board does, in 1-3 sentences.

board:
  layers: 2
  outline: {shape: rect, width_mm: 40, height_mm: 30}  # optional — see note below
  mounting_holes: [{x_mm: 3, y_mm: 3, drill_mm: 2.2}]  # requires explicit outline (see note)

libraries: []                # extra library paths, see library.md

parts:
  U1: {part: "lcsc:C77964"}  # designator -> `part:` (catalog) OR `class:` (never both)

nets:
  V3V3: [U1.vdd, C1.p1]      # designator.logical_role (not physical pin)

intents:
  - {type: power_rail, net: V3V3, voltage_v: 3.3, max_current_a: 0.5}

placement_hints:
  - {part: U1, region_pref: center}
```

## `board.outline`: optional — automatic if omitted

Omit `outline` when the application does **not** impose a board geometry (no fixed real
enclosure). The placer figures out on its own the smallest 4:3 rectangle that fits the layout
without overlap/keepout violations — no need to guess a size and shrink it by trial and error.
Declare `outline` explicitly when: there is a real enclosure with fixed dimensions; the board
needs to fit a standardized slot/connector; or you already know the size for some other concrete
reason. `mounting_holes` with explicit coordinates **require** an explicit `outline` (a fixed hole
assumes known geometry — the schema rejects the combination of absent `outline` plus present
`mounting_holes`). For a minimum floor without fixing the final size, use
`outline: {..., growable: true}` — the placer never produces a result smaller than the declared
size, but may grow beyond it.

## `parts`: `part:` vs `class:`

- `part: "lcsc:CXXXXX"` — a real catalog instance (has an MPN, physical pinout, possible
  geometry). Requires a descriptor in `library/parts/`; if absent, generates a warning, not an
  error (see `workflow.md`).
- `class: <id>` — only the electrical behavior of the class, no physical instance yet. Use when
  the user hasn't decided on an exact MPN, or for conceptual prototypes.
- **Never both at once** — the schema rejects it.

## `nets`: logical role, not physical pin

`U1.vdd` references the **role** declared in the class's `pins:` (`vdd`, `gnd`, `swdio`, ...), not
the chip's physical pin number. The role→physical-pin mapping lives in `pinout:` of the object
descriptor (`library/parts/`), filled in from the datasheet.

## `intents` vocabulary (extensible, but start with these)

| `type` | Fields | Use |
|---|---|---|
| `power_rail` | `net`, `voltage_v`, `max_current_a?` | Declares a net as a power source — feeds the power-tree check |
| `diff_pair` | `nets: [a, b]`, `impedance_ohm?` | Differential pair (USB, CAN, ...) |
| `decouples` | `part`, `target` (`designator.role`), `max_distance_mm?` | Decoupling capacitor — avoids `W_MISSING_DECOUPLING` |
| `high_current` | `net`, `current_a` | Net that needs a wide trace — feeds the current-budget check |
| `analog_sensitive` | `nets: [...]` | Noise-sensitive analog signal — documentational only today |

Discover the exact schema with `fae schema intent` at any time — don't rely on memory for
optional fields.

## `placement_hints`: preference, not position

- `{part: X, region_pref: north\|south\|east\|west\|center}` — preferred zone in the coarse-grid
  floorplan.
- `{part: X, anchor: "edge_south"}` — free-form string; if it contains one of the zone names, it
  also influences the zone.
- `{part: X, near: Y, max_distance_mm: N}` — proximity preference between two domains; a
  violation becomes a warning on the placement candidate, does not block.
- `{domain: <block_namespace>, region_pref: ...}` — applies the hint to every part of an imported
  block (`imports:`), not to a single part.

## Reusable blocks (`imports`)

```yaml
imports:
  - path: blocks/power_supply
```

The block is another `intent.yaml` with `kind: block` (no `board` section). Block designators
enter the same namespace as the root project (a collision becomes a hard `E_DUPLICATE_DESIGNATOR`
error, not a silent one).

## Before considering it done

Run `fae validate` and read every item returned — don't assume "looks right" is enough. Errors
block; warnings don't block but should be resolved or explicitly accepted by the user.
