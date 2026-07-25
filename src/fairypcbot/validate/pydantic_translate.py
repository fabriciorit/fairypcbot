"""Tradução de erros nativos do pydantic para `ValidationErrorItem` (código estável + PT)."""

from __future__ import annotations

from pydantic import ValidationError

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem


def _loc_to_path(loc: tuple) -> str:
    parts = []
    for item in loc:
        if isinstance(item, int):
            parts[-1] = f"{parts[-1]}[{item}]" if parts else f"[{item}]"
        else:
            parts.append(str(item))
    return ".".join(parts) if parts else "$"


def translate_pydantic_errors(exc: ValidationError) -> list[ValidationErrorItem]:
    items: list[ValidationErrorItem] = []
    for err in exc.errors():
        path = _loc_to_path(err["loc"])
        err_type = err["type"]
        if err_type == "missing":
            code = ErrorCode.E_SCHEMA_MISSING_FIELD
            suggestion = f"Adicione o campo obrigatório em '{path}'"
        elif err_type in ("literal_error", "enum"):
            code = ErrorCode.E_SCHEMA_INVALID_VALUE
            expected = err.get("ctx", {}).get("expected", "")
            suggestion = f"Use um dos valores aceitos em '{path}'" + (
                f": {expected}" if expected else ""
            )
        elif err_type == "extra_forbidden":
            code = ErrorCode.E_SCHEMA_INVALID
            suggestion = f"Remova o campo desconhecido em '{path}' (não faz parte do schema)"
        elif err_type == "union_tag_invalid" or err_type == "union_tag_not_found":
            code = ErrorCode.E_INTENT_UNKNOWN_TYPE
            suggestion = "Verifique o campo 'type' — consulte 'fairypcbot schema intent'"
        else:
            code = ErrorCode.E_SCHEMA_INVALID
            suggestion = f"Corrija o valor em '{path}' conforme o schema"
        items.append(
            ValidationErrorItem(
                path=path,
                code=code,
                message=err["msg"],
                suggestion=suggestion,
            )
        )
    return items
