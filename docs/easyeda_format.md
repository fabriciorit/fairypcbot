# Subset of the EasyEDA format used by fairypcbot

fairypcbot uses the public EasyEDA API (`https://easyeda.com/api/products/{lcsc_id}/components`)
as a catalog data source (spec, section 7) and, as an emission target
(`emit/easyeda_std.py`). This document covers the subset of the format the framework actually
interprets — not a complete EasyEDA specification.

**Engineering reference**: the [easyeda2kicad](https://github.com/uPesy/easyeda2kicad.py) project
did public reverse engineering of this format; that knowledge is used as a reference (not a
dependency — nothing in fairypcbot imports easyeda2kicad code).

## Provenance note on the footprint parser

The footprint parser (`catalog/easyeda_footprint.py`) was implemented from the **publicly
documented** format. Before relying on the resulting geometry for anything that depends on
dimensional precision (routing, fabrication), validate it against at least one real import in
EasyEDA/KiCad. See `docs/limitations.md`.

## Footprint shape lines (`dataStr.shape`)

Each element of `result.packageDetail.dataStr.shape` (or, in responses where the footprint is
already embedded, `result.dataStr.shape`) is a string with fields separated by `~`. The first
field is the element type:

| Type | Interpreted by fairypcbot? |
|---|---|
| `PAD` | Yes — the only type used (pin geometry) |
| `TRACK`, `ARC`, `CIRCLE`, `SOLIDREGION`, `TEXT`, `HOLE`, `VIA` | No (silently ignored) |

Field layout of a `PAD` line (best-effort, see note above):

```
PAD~shape~center_x~center_y~width~height~layer~net~number~hole_radius~points~rotation~id~hole_length~...
```

- `shape`: `ELLIPSE` \| `RECT` \| `OVAL` \| `POLYGON`
- `center_x`, `center_y`, `width`, `height`: in EasyEDA units (see unit conversion below)
- `layer`: numeric EasyEDA layer id (`1`=top copper, `2`=bottom copper, `11`=multi-layer/
  through-hole — other ids are kept as a raw string)
- `number`: pin designator (not always a semantic role like `vdd`/`gnd` — not used to fill in
  `pinout`, only for geometry)
- `hole_radius`: > 0 for THT (through-hole) pads; 0 or absent for SMD
- `rotation`: degrees

Fields beyond `rotation` (internal id, oval hole length, etc.) are not used.

### Unit conversion

```python
EASYEDA_UNIT_TO_MM = 10 * 0.0254  # 10 mil per unit = 0.254 mm/unit
```

This is the factor documented by easyeda2kicad.

## Document envelope — emission (`emit/easyeda_std.py`, confirmed against real data)

Unlike the section above (footprint reading, still best-effort), the envelope used to **emit**
`board.json` was reconstructed from real, authentic documents obtained from the EasyEDA API
(local cache from `catalog fetch`) — not third-party reverse engineering. A complete EasyEDA
document (footprint or PCB) has the shape:

```json
{
  "head": {"docType": "4", "editorVersion": "6.5.51", "x": 4000, "y": 3000, "...": "..."},
  "canvas": "CA~1000~1000~#000000~yes~#FFFFFF~10~1000~1000~line~0.19685~mm~0.7874~45~visible~0.5~4000~3000~0~none",
  "layers": ["1~TopLayer~#FF0000~true~false~true~", "..."],
  "objects": ["All~true~false", "..."],
  "BBox": {"x": 3982.1, "y": 2996.7, "width": 35.8, "height": 6.9},
  "shape": ["TRACK~0.7874~3~~3995.4482 2996.6536 3995.4482 3003.5433~gge162~0", "..."]
}
```

Confirmed by direct comparison against a real footprint document: canvas origin at
`(4000, 3000)`, unit `1 unit = 10 mil = 0.254mm` (factor above, now confirmed rather than only
documented), `TRACK` with space-separated point pairs (no comma between x and y), `PAD` with a
`plated` field (`Y`/`N`) at index 15 and comma-separated `hole_center` (`"x,y"`) when a hole is
present. **Not confirmed**: the correct `head.docType` for a complete PCB document (a third-party
convention of `"5"` is used — only a real footprint sample, docType `"4"`, and a symbol sample,
docType `"2"`, are available).

## EasyEDA Pro (`.eprj2`, native emission — `emit/easyeda_pro.py`)

The **EasyEDA Pro (desktop)** editor uses a project format completely different from Std: a
**SQLite** database (`.eprj2` extension), not a single shapes JSON. `fae emit --target easyeda_pro`
generates that file directly — the user opens it in Pro without going through any import/
conversion step (the Std→Pro converter built into the editor has been observed to silently drop
nets/devices).

Structure confirmed from a real project file: tables `projects`/`branches`/`schematics`/
`documents`/`components`/`devices`/`attributes`; `documents.dataStr`/`components.dataStr` are text
(`"base64" + base64(gzip(...))`) with one JSON-array line per element (`COMPONENT`, `ATTR`,
`PAD_NET`, `PAD`, `NET`, ...). Unit = 1 mil = 0.0254mm (different from Std, which uses 10
mil/unit). Some details remain unconfirmed (THT pads, board outline).

### Symbol shape lines (`dataStr.shape`, same endpoint as the footprint)

The SAME `result.dataStr` from the public API (used for footprint) is, in fact, the complete
**symbol** document (docType `"2"`) — no extra API call is needed. Types interpreted by
`catalog/easyeda_symbol.py`:

| Type | Interpreted? |
|---|---|
| `P` (pin) | Yes — number, name, position, rotation (fields 3-6 plus the name via regex on the `^^` block) |
| `PL` (open polyline) | Yes — space-separated points in a single field |
| `PT` (closed path, e.g. diode arrow) | Yes — only `M`/`L`/`Z` commands; arcs/curves not supported |
| `R` (body rectangle) | Yes — converted into a closed 4-point polyline |
| others (`E` ellipse, `A` arc, `T` free text) | No |

Confirmed against two real cached responses: a 1N4148 diode (2 pins `A`/`C` plus body/arrow) and
an LM386 (8 named pins `BYPASS`/`GAIN`/`IN+`/`IN-`/`GND`/`VS`/`VOUT` plus a body rectangle). Same
unit conversion factor as the footprint (`EASYEDA_UNIT_TO_MM`, 10 mil/unit).

### SYMBOL document on emission (`.eprj2`, `emit/easyeda_pro.py::_symbol_doc_lines`)

One SYMBOL doc (docType 2) per device, with `PIN`/`ATTR`(`NAME`/`NUMBER`)/`POLY` in the compact
format confirmed against a real document. The schematic sheet (docType 1) is populated with real
`COMPONENT`+`WIRE` entries — some parts remain best-effort (POLY closure, layout without
clustering, net label without a native port).

## What fairypcbot does NOT interpret (yet)

- The schematic symbol (`dataStr` of the part itself, when it's the symbol rather than the
  footprint) — only the `c_para.Manufacturer`/`c_para.package` attributes are read, for the
  `manufacturer`/`package.name` fields of the stub generated by `catalog fetch`.
- Silkscreen, copper pour, solder-mask layers — only pad position/size.
- The separate footprint-UUID resolution step (some EasyEDA components reference their footprint
  by a separate UUID, requiring a second API call). The current resolver tries to extract `shape`
  directly from the same response; if the live API requires that second step,
  `EasyedaResolver._extract_footprint_shape_lines` returns `None` and fairypcbot degrades
  gracefully to "no geometry" (`footprint: null`, `provenance.footprint: missing`) instead of
  failing — but this means that, until that second step is implemented, `catalog fetch` may bring
  back no footprint at all for parts that use this pattern.
