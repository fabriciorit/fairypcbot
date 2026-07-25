"""User confirmation of items extracted from a datasheet (`fae datasheet review`)."""

from __future__ import annotations

from dataclasses import dataclass

from fairypcbot.schemas.datasheet import DatasheetExtract, ExtractedItem

_LIST_SECTIONS = [
    "identification",
    "absolute_maximum",
    "operating_conditions",
    "electrical",
    "pinout",
    "function_tables",
    "formulas",
    "layout_guidance",
    "thermal",
    "reflow",
    "curves",
    "behaviors",
]


@dataclass
class UnverifiedItem:
    section: str
    index: int
    status: str
    summary: str


def _summarize(item: ExtractedItem) -> str:
    for attr in ("key", "symbol", "param", "pin_name", "name", "title", "text"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return item.__class__.__name__


def collect_unverified(datasheet: DatasheetExtract) -> list[UnverifiedItem]:
    unverified: list[UnverifiedItem] = []
    for section in _LIST_SECTIONS:
        items: list[ExtractedItem] = getattr(datasheet, section)
        for index, item in enumerate(items):
            if item.verified_by is None:
                unverified.append(
                    UnverifiedItem(
                        section=section, index=index, status=item.extraction_status, summary=_summarize(item)
                    )
                )
    return unverified


def mark_verified(datasheet: DatasheetExtract, section: str, index: int) -> None:
    items: list[ExtractedItem] = getattr(datasheet, section)
    items[index].verified_by = "user"


def mark_all_verified(datasheet: DatasheetExtract) -> int:
    count = 0
    for section in _LIST_SECTIONS:
        for item in getattr(datasheet, section):
            if item.verified_by is None:
                item.verified_by = "user"
                count += 1
    return count
