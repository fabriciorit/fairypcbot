"""Datasheet ingestion (M7): hash + per-page text extraction + checklist skeleton.

The framework never interprets the PDF content — it only hashes, extracts raw text (to cut the cost
of the LLM's reading), and builds the skeleton of what needs to be filled in, derived from the
class's `params.required` and the arguments of the sizing functions it references. The LLM is the
one that reads and fills it in, following `docs/llm/datasheet-extraction.md`.
"""
