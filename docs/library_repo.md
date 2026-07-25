# Library repository pattern

A fairypcbot "library" is any directory with this layout — it can live inside a project's repo, in
its own git repository (shared via GitHub, GitLab, an internal server, or a USB drive), or in both
at once. The framework makes no distinction between "the framework's own library" and "a
third-party library": all of them are discovered and combined the same way (see the Resolution
section below).

## Layout

```
my-library/
├── library.yaml        # optional — manifest (name, description, version)
├── classes/             # component_class — electrical/logical vocabulary (pin roles, params)
├── parts/                # component_part — real instances (MPN, pinout, package reference)
├── packages/              # component_package — geometry (families with variants, see below)
├── datasheets/             # datasheet_extract — structured extractions from PDFs
└── blocks/                  # reusable intent.yaml files (`imports` section of another intent.yaml)
```

No subdirectory is mandatory — a library with only `classes/`, for example, is valid.

This root repository intentionally does not version vendor `parts/` data: records obtained via
`fae catalog fetch` (MPN, pinout, package reference, provenance) live in the user's local cache,
outside the repository, since that data changes per project and per vendor snapshot. Individual
projects are free to keep their own `library/parts/` directory to version curated, hand-completed
descriptors if they want that data tracked in git.

### `library.yaml` (manifest, optional)

```yaml
name: my-library
description: Curated components for industrial automation projects
version: "1.2.0"
```

Not consumed by any validation today — it's metadata for humans (and for future
version/compatibility resolution between libraries).

### `packages/` — families, not standalone geometries

One file per family (`packages/soic-8.yaml`, not one file per variant) — families contain
`variants:`, each with its own geometry and provenance. See `schemas/component_package.py` and the
examples under `library/packages/` in this repository.

### `datasheets/` — one file per MPN family

A `datasheet_extract` usually covers an entire family (e.g. `CH32V203C8T6`, `CH32V203C6T6`,
`CH32V203CBT6` share the same datasheet) — avoid duplicating the extraction per MPN variant; list
them in `mpn_family`. See `docs/llm/datasheet-extraction.md`.

## Resolution (how the framework combines multiple libraries)

`validate/library.py::resolve_library_paths` combines libraries in this precedence order (the
first library to define an `id` wins, when two define the same id):

1. `<project>/library/` — the project's local library, if it exists.
2. Each path listed in `libraries:` in the root `intent.yaml` (relative to the project, or
   absolute):

   ```yaml
   libraries:
     - ../my-shared-library
     - /opt/pcb-libs/fairypcbot-industrial
   ```

3. The fairypcbot repository's own `library/`, when the project is nested inside it (as the
   `examples/` in this repo are) — this is how the examples work without needing to copy the
   founding library.

## Sharing a library (manual git — deliberate)

The framework **does not clone or update git repositories**. This is a deliberate choice: an
embedded git clone/pull adds network access, authentication, and conflict resolution as framework
responsibilities, with no proportional gain — `git clone`/`git pull` are trivial steps for the
user to run.

Recommended flow:

```bash
git clone https://github.com/someone/fairypcbot-library-industrial ../my-library
```

Then reference `../my-library` in `libraries:` in `intent.yaml`.

## Scale

YAML plus git scales well to tens of thousands of text files — there is no need for a binary or
compressed format (that would break diffing/human review/LLM authorship, for a problem that
doesn't exist yet). Datasheet PDFs **never enter the repository**: only the reference
(`source_pdf.path_or_url`) and the file's sha256. The real bottleneck, if it ever appears, is the
time to load every YAML file in a large library (`LibraryIndex` does *eager parsing* of
everything) — the fix, when needed, is lazy loading by filename-equals-id convention (without
changing the file format). Not implemented at this stage.
