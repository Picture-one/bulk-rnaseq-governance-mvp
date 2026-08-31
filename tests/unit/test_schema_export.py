import json
from pathlib import Path

from scripts.export_schemas import export_schemas

EXPECTED_SCHEMA_FILES = {
    "dataset_definition.schema.json",
    "file_definition.schema.json",
    "method_definition.schema.json",
    "reference_definition.schema.json",
    "reference_file_definition.schema.json",
    "sample_definition.schema.json",
    "stage_definition.schema.json",
    "validation_policy.schema.json",
}


def test_export_schemas_writes_expected_deterministic_files(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "schemas"

    first_paths = export_schemas(output_dir)
    first_snapshot = {
        path.name: path.read_bytes()
        for path in first_paths
    }

    second_paths = export_schemas(output_dir)
    second_snapshot = {
        path.name: path.read_bytes()
        for path in second_paths
    }

    assert {path.name for path in first_paths} == EXPECTED_SCHEMA_FILES
    assert first_snapshot == second_snapshot

    dataset_schema = json.loads(
        (output_dir / "dataset_definition.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert dataset_schema["title"] == "DatasetDefinition"
    assert dataset_schema["additionalProperties"] is False
