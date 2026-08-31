from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from rnaseq_mvp.models import (
    DatasetDefinition,
    FileDefinition,
    MethodDefinition,
    ReferenceDefinition,
    ReferenceFileDefinition,
    SampleDefinition,
    StageDefinition,
    ValidationPolicy,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "dataset_definition.schema.json": DatasetDefinition,
    "file_definition.schema.json": FileDefinition,
    "method_definition.schema.json": MethodDefinition,
    "reference_definition.schema.json": ReferenceDefinition,
    "reference_file_definition.schema.json": ReferenceFileDefinition,
    "sample_definition.schema.json": SampleDefinition,
    "stage_definition.schema.json": StageDefinition,
    "validation_policy.schema.json": ValidationPolicy,
}


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []

    for filename in sorted(SCHEMA_MODELS):
        model_type = SCHEMA_MODELS[filename]
        schema = model_type.model_json_schema()
        serialized = json.dumps(
            schema,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

        destination = output_dir / filename
        destination.write_text(
            f"{serialized}\n",
            encoding="utf-8",
        )
        written_paths.append(destination)

    return written_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export deterministic JSON Schema snapshots."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("schemas"),
        help="Directory receiving generated schema files.",
    )
    arguments = parser.parse_args()

    for path in export_schemas(arguments.output_dir):
        print(path)


if __name__ == "__main__":
    main()
