from __future__ import annotations

import io

from ruamel.yaml import YAML

from fairypcbot.schemas.base import FairyBaseModel
from fairypcbot.schemas.component_package import ComponentPackage
from fairypcbot.schemas.component_part import ComponentPart
from fairypcbot.schemas.datasheet import DatasheetExtract

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


def dump_model(model: FairyBaseModel) -> str:
    data = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    buf = io.StringIO()
    _yaml.dump(data, buf)
    return buf.getvalue()


def dump_component_part(part: ComponentPart) -> str:
    return dump_model(part)


def dump_component_package(package: ComponentPackage) -> str:
    return dump_model(package)


def dump_datasheet_extract(datasheet: DatasheetExtract) -> str:
    return dump_model(datasheet)
