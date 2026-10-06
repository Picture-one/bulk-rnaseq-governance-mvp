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


def test_dataset_definition_accepts_rrna_depletion_single_end() -> None:
    from rnaseq_mvp.models import DatasetDefinition, FileDefinition, SampleDefinition

    dataset = DatasetDefinition(
        schema_version="1.0",
        dataset_id="GEO_RRNA_TEST",
        profile_id="human_illumina_rrna_depletion_bulk_v1",
        source_database="GEO",
        experiment_accession="GSE_TEST",
        organism="Homo sapiens",
        biosample="whole blood",
        assay="RNA-seq",
        library_selection="rRNA depletion",
        read_layout="single-end",
        read_length=101,
        strandedness="auto",
        sequencing_platform="Illumina",
        sequencing_center="TEST_CENTER",
        samples=[
            SampleDefinition(
                sample_id="S1",
                biological_replicate=1,
                biosample_accession="SAMN_TEST",
                library_accession="SRX_TEST",
                files=[
                    FileDefinition(
                        role="R1",
                        file_accession="SRR_TEST",
                        filename="S1_R1.fastq.gz",
                        url="https://example.org/S1_R1.fastq.gz",
                        expected_bytes=10,
                        expected_md5="a" * 32,
                    )
                ],
            )
        ],
    )

    assert dataset.profile_id == "human_illumina_rrna_depletion_bulk_v1"
    assert dataset.samples[0].read_files_by_role()["R1"].filename == "S1_R1.fastq.gz"


def test_method_definition_accepts_longread_gene_counts() -> None:
    from rnaseq_mvp.models import MethodDefinition

    method = MethodDefinition(
        schema_version="1.0",
        method_profile_id="longread_rnaseq_minimap2_gene_counts_v1",
        method_family="longread_gene_counts",
        nextflow_version=None,
        pipeline_name="custom-longread-gene-counts",
        pipeline_version="0.1.0",
        aligner="minimap2",
        quantifier="featureCounts",
        aggregation="gene_assignment",
        counts_measure_type="assigned_longread_gene_counts",
    )

    assert method.method_family == "longread_gene_counts"


def test_dataset_definition_accepts_ont_longread_cdna() -> None:
    from rnaseq_mvp.models import DatasetDefinition, FileDefinition, SampleDefinition

    dataset = DatasetDefinition(
        schema_version="1.0",
        dataset_id="GEO_LONGREAD_TEST",
        profile_id="human_longread_rnaseq_v1",
        source_database="GEO",
        experiment_accession="GSE_LONG",
        organism="Homo sapiens",
        biosample="islet",
        assay="long-read RNA-seq",
        library_selection="cDNA",
        read_layout="long-read",
        read_length=1000,
        strandedness="auto",
        sequencing_platform="ONT",
        sequencing_center="TEST_CENTER",
        samples=[
            SampleDefinition(
                sample_id="LR1",
                biological_replicate=1,
                biosample_accession="SAMN_LONG",
                library_accession="SRX_LONG",
                files=[
                    FileDefinition(
                        role="R1",
                        file_accession="SRR_LONG",
                        filename="LR1.fastq.gz",
                        url="https://example.org/LR1.fastq.gz",
                        expected_bytes=10,
                        expected_md5="b" * 32,
                    )
                ],
            )
        ],
    )

    assert dataset.profile_id == "human_longread_rnaseq_v1"
    assert dataset.sequencing_platform == "ONT"


def test_dataset_definition_rejects_pacbio_for_longread_v1() -> None:
    from rnaseq_mvp.models import DatasetDefinition, FileDefinition, SampleDefinition

    with pytest.raises(ValidationError, match="long-read v1 supports ONT"):
        DatasetDefinition(
            schema_version="1.0",
            dataset_id="PACBIO_LONGREAD_TEST",
            profile_id="human_longread_rnaseq_v1",
            source_database="GEO",
            experiment_accession="GSE_PACBIO",
            organism="Homo sapiens",
            biosample="islet",
            assay="long-read RNA-seq",
            library_selection="cDNA",
            read_layout="long-read",
            read_length=1000,
            strandedness="auto",
            sequencing_platform="PacBio",
            samples=[
                SampleDefinition(
                    sample_id="PB1",
                    biological_replicate=1,
                    biosample_accession="SAMN_PB",
                    library_accession="SRX_PB",
                    files=[
                        FileDefinition(
                            role="R1",
                            file_accession="SRR_PB",
                            filename="PB1.fastq.gz",
                            url="https://example.org/PB1.fastq.gz",
                            expected_bytes=10,
                            expected_md5="c" * 32,
                        )
                    ],
                )
            ],
        )
