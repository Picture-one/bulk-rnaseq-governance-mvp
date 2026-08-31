from pathlib import Path

import pytest
from pydantic import ValidationError

from rnaseq_mvp.definitions import DefinitionRegistry


def test_registry_rejects_stage_with_unknown_dataset(tmp_path: Path) -> None:
    root = tmp_path / "definitions"
    (root / "stages").mkdir(parents=True)

    (root / "stages" / "T2A.yaml").write_text(
        """
schema_version: '1.0'
stage_id: T2A
dataset_id: missing_dataset
sample_ids: [K562_POLYA_REP1]
reference_profile_id: human_grch38_gencode_v50_primary
method_profile_id: bulk_rnaseq_star_salmon_v1
validation_policy_id: bulk_rnaseq_t2_v1
expected_outputs: [gene_counts_raw_estimated]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown dataset_id: missing_dataset"):
        DefinitionRegistry.load(root)


def test_file_definition_rejects_invalid_md5() -> None:
    from rnaseq_mvp.models import FileDefinition

    with pytest.raises(ValidationError):
        FileDefinition(
            role="R1",
            file_accession="ENCFF001RED",
            filename="ENCFF001RED.fastq.gz",
            url="https://www.encodeproject.org/file.fastq.gz",
            expected_bytes=10,
            expected_md5="not-md5",
        )
