from __future__ import annotations

from datetime import UTC, datetime

from fairypcbot.schemas.component_part import ComponentPart, PackageSpec
from fairypcbot.schemas.provenance import Provenance


def test_component_part_allows_missing_class_and_pinout():
    part = ComponentPart(
        kind="component_part",
        id="lcsc:C1",
        class_=None,
        mpn="X",
        manufacturer="Y",
        package=PackageSpec(name="SOIC-8", source="easyeda"),
        provenance={
            "class": Provenance(source="missing", timestamp=datetime.now(UTC)),
        },
    )
    assert part.class_ is None
    assert part.pinout == {}
    assert part.provenance["class"].source == "missing"
