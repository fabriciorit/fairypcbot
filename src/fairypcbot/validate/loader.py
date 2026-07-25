"""Loading of `intent.yaml` and recursive resolution of `imports` (spec section 3.1/10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML, YAMLError

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.intent import Intent, PartSpec

_yaml = YAML(typ="safe")


class YamlSyntaxError(Exception):
    def __init__(self, path: Path, original: Exception):
        self.path = path
        self.original = original
        super().__init__(str(original))


def load_yaml(path: Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = _yaml.load(text)
    except (YAMLError, OSError) as exc:
        raise YamlSyntaxError(path, exc) from exc
    if not isinstance(data, dict):
        raise YamlSyntaxError(path, ValueError("o documento YAML raiz deve ser um mapeamento"))
    return data


@dataclass
class ImportedBlock:
    namespace: str
    intent: Intent
    path: Path


@dataclass
class ProjectGraph:
    root: Intent
    root_path: Path
    blocks: list[ImportedBlock] = field(default_factory=list)
    errors: list[ValidationErrorItem] = field(default_factory=list)

    def combined_parts(self) -> tuple[dict[str, PartSpec], list[ValidationErrorItem]]:
        """Root designators + imported block designators, without namespace prefix (following the
        spec example, where `PS1.VIN` is referenced directly in root `nets`). Name collisions
        become E_DUPLICATE_DESIGNATOR, suggesting the block namespace as a fix.
        """
        combined: dict[str, PartSpec] = dict(self.root.parts)
        dup_errors: list[ValidationErrorItem] = []
        for block in self.blocks:
            for designator, spec in block.intent.parts.items():
                if designator in combined:
                    dup_errors.append(
                        ValidationErrorItem(
                            path=f"imports[{block.namespace}].parts.{designator}",
                            code=ErrorCode.E_DUPLICATE_DESIGNATOR,
                            message=(
                                f"Designador '{designator}' do bloco '{block.namespace}' colide "
                                f"com um designador já existente"
                            ),
                            suggestion=(
                                f"Renomeie para '{block.namespace}.{designator}' em um dos dois "
                                f"locais, ou ajuste o designador na origem"
                            ),
                        )
                    )
                    continue
                combined[designator] = spec
        return combined, dup_errors


def resolve_imports(root_path: Path, root_intent: Intent) -> ProjectGraph:
    graph = ProjectGraph(root=root_intent, root_path=Path(root_path))
    _walk_imports(root_path, root_intent, graph, visited=[Path(root_path).resolve()])
    return graph


def _walk_imports(
    base_path: Path, intent: Intent, graph: ProjectGraph, visited: list[Path]
) -> None:
    for imp in intent.imports:
        block_dir = (Path(base_path) / imp.path).resolve()
        intent_file = block_dir / "intent.yaml"
        if not intent_file.exists():
            graph.errors.append(
                ValidationErrorItem(
                    path=f"imports[{imp.path}]",
                    code=ErrorCode.E_IMPORT_NOT_FOUND,
                    message=f"Bloco importado '{imp.path}' não encontrado (esperado {intent_file})",
                    suggestion="Verifique o caminho em 'imports' ou crie o intent.yaml do bloco",
                )
            )
            continue
        if block_dir in visited:
            chain = " -> ".join(str(p) for p in [*visited, block_dir])
            graph.errors.append(
                ValidationErrorItem(
                    path=f"imports[{imp.path}]",
                    code=ErrorCode.E_IMPORT_CYCLE,
                    message=f"Ciclo de imports detectado: {chain}",
                    suggestion="Remova a dependência circular entre os blocos",
                )
            )
            continue

        try:
            raw = load_yaml(intent_file)
        except YamlSyntaxError as exc:
            graph.errors.append(
                ValidationErrorItem(
                    path=f"imports[{imp.path}]",
                    code=ErrorCode.E_YAML_SYNTAX,
                    message=f"Erro de sintaxe YAML em {intent_file}: {exc.original}",
                    suggestion="Corrija a sintaxe do YAML do bloco importado",
                )
            )
            continue

        try:
            child_intent = Intent.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — translated by the runner for the root block too
            graph.errors.append(
                ValidationErrorItem(
                    path=f"imports[{imp.path}]",
                    code=ErrorCode.E_SCHEMA_INVALID,
                    message=f"Schema inválido em {intent_file}: {exc}",
                    suggestion="Corrija o intent.yaml do bloco importado conforme o schema",
                )
            )
            continue

        namespace = Path(imp.path).name
        graph.blocks.append(ImportedBlock(namespace=namespace, intent=child_intent, path=block_dir))
        _walk_imports(block_dir, child_intent, graph, [*visited, block_dir])
