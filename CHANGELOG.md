# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-25

### Added

- Intent-driven PCB design pipeline: `validate` → `elaborate` → `place` → `emit` → `routecheck`.
- Pydantic-based schemas for intent, component classes, packages, parts, and the intermediate representation (IR).
- Domain-based automatic placement with multiple heuristics (compact, spread, balanced).
- EasyEDA Pro and Specctra DSN emitters.
- Routability estimation via headless Freerouting integration.
- LCSC/EasyEDA catalog resolution (`fae catalog fetch`).
- Datasheet ingestion (`fae datasheet ingest`) with structured YAML extraction.
- JSONL audit trail with SHA-256 provenance tracking.
- Founding library: 29 component classes and 3 generic packages (CC0-1.0).
- LLM integration contract (`docs/llm/`) with progressive disclosure and size constraints.
- Two examples: `led_blinker_555` (offline) and `metal_detector_bfo` (requires fetch).
