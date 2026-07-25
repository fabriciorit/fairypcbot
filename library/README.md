# fairypcbot — founding library

Authorial component descriptors for the fairypcbot framework.

## Structure

- `classes/` — component class definitions (pin roles, parameters, validation rules)
- `packages/` — generic footprints (IPC-7351 nominal dimensions)

## License

All content in this directory is in the **public domain** (CC0-1.0).
See the `LICENSE` file for the full text.

Component descriptors are released under CC0-1.0 for maximum interoperability with other
EDA tools and libraries.

The framework code itself (outside this directory) is licensed under Apache-2.0.

## Provenance rule

Only artifacts with `provenance.source: user` (or with no explicit provenance field) are
accepted in this directory. Vendor-sourced data (`source: easyeda`, `source: datasheet`)
**must not be committed** — it is obtained on demand via `fae catalog fetch` and stored
in the user's local cache (`~/.cache/fairypcbot/`).
