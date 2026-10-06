from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    HttpUrl,
    PositiveInt,
    field_validator,
    model_validator,
)

_MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _validated_md5(value: str) -> str:
    if not _MD5_PATTERN.fullmatch(value):
        raise ValueError("expected_md5 must be 32 lowercase hexadecimal characters")
    return value


class StrictDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ReadRole = Literal["R1", "R2"]


class FileDefinition(StrictDefinitionModel):
    role: ReadRole
    file_accession: str
    filename: str
    url: HttpUrl
    expected_bytes: PositiveInt
    expected_md5: str

    @field_validator("expected_md5")
    @classmethod
    def validate_expected_md5(cls, value: str) -> str:
        return _validated_md5(value)


class SampleDefinition(StrictDefinitionModel):
    sample_id: str
    biological_replicate: PositiveInt
    biosample_accession: str
    library_accession: str
    files: list[FileDefinition]

    def read_files_by_role(self) -> dict[ReadRole, FileDefinition]:
        return {file.role: file for file in self.files}

    @model_validator(mode="after")
    def validate_read_files(self) -> SampleDefinition:
        roles = [file.role for file in self.files]

        if roles.count("R1") != 1:
            raise ValueError("sample must contain exactly one R1")
        if roles.count("R2") > 1:
            raise ValueError("sample must not contain more than one R2")
        if len(roles) not in (1, 2):
            raise ValueError("sample must contain one R1 and optional one R2")

        return self


class DatasetDefinition(StrictDefinitionModel):
    schema_version: Literal["1.0"]
    dataset_id: str
    profile_id: Literal[
        "human_illumina_polya_bulk_v1",
        "human_illumina_rrna_depletion_bulk_v1",
        "human_longread_rnaseq_v1",
    ] = "human_illumina_polya_bulk_v1"
    source_database: Literal["ENCODE", "GEO", "SRA", "ENA", "USER_UPLOAD"]
    experiment_accession: str
    organism: Literal["Homo sapiens"]
    biosample: str
    assay: Literal["polyA plus RNA-seq", "RNA-seq", "long-read RNA-seq"]
    library_selection: Literal["Poly(A)+", "rRNA depletion", "direct RNA", "cDNA"]
    read_layout: Literal["paired-end", "single-end", "long-read"]
    read_length: PositiveInt
    strandedness: Literal["reverse", "forward", "unstranded", "auto", "unknown"]
    sequencing_platform: str
    sequencing_center: str = "UNKNOWN"
    samples: list[SampleDefinition]

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> DatasetDefinition:
        sample_ids = [sample.sample_id for sample in self.samples]

        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("dataset sample_ids must be unique")

        file_accessions = [
            file.file_accession
            for sample in self.samples
            for file in sample.files
        ]

        if len(file_accessions) != len(set(file_accessions)):
            raise ValueError("dataset file_accessions must be unique")

        for sample in self.samples:
            roles = sample.read_files_by_role()
            if self.read_layout == "paired-end" and set(roles) != {"R1", "R2"}:
                raise ValueError("paired-end samples must contain exactly one R1 and one R2")
            if self.read_layout in {"single-end", "long-read"} and set(roles) != {"R1"}:
                raise ValueError(f"{self.read_layout} samples must contain exactly one R1")

        if self.profile_id == "human_longread_rnaseq_v1":
            if self.read_layout != "long-read":
                raise ValueError("long-read v1 requires read_layout=long-read")
            if self.sequencing_platform != "ONT":
                raise ValueError("long-read v1 supports ONT only")
            if self.library_selection not in {"cDNA", "direct RNA"}:
                raise ValueError("long-read v1 requires cDNA or direct RNA")

        return self


class ReferenceFileDefinition(StrictDefinitionModel):
    role: Literal["genome_fasta", "annotation_gtf"]
    filename: str
    url: HttpUrl
    expected_bytes: PositiveInt
    expected_md5: str

    @field_validator("expected_md5")
    @classmethod
    def validate_expected_md5(cls, value: str) -> str:
        return _validated_md5(value)


class ReferenceDefinition(StrictDefinitionModel):
    schema_version: Literal["1.0"]
    reference_profile_id: str
    organism: Literal["Homo sapiens"]
    genome_build: Literal["GRCh38"]
    assembly_patch: Literal["p14"]
    annotation_provider: Literal["GENCODE"]
    annotation_release: Literal["50"]
    assembly_scope: Literal["primary_assembly"]
    files: list[ReferenceFileDefinition]


class StageDefinition(StrictDefinitionModel):
    schema_version: Literal["1.0"]
    stage_id: Literal["T2A", "T2B"]
    dataset_id: str
    sample_ids: list[str]
    reference_profile_id: str
    method_profile_id: str
    validation_policy_id: str
    expected_outputs: list[str]

    @model_validator(mode="after")
    def validate_sample_ids(self) -> StageDefinition:
        if not self.sample_ids:
            raise ValueError("stage sample_ids must not be empty")

        if len(self.sample_ids) != len(set(self.sample_ids)):
            raise ValueError("stage sample_ids must be unique")

        return self


class MethodDefinition(StrictDefinitionModel):
    schema_version: Literal["1.0"]
    method_profile_id: str
    method_family: Literal["shortread_star_salmon", "longread_gene_counts"] = (
        "shortread_star_salmon"
    )
    nextflow_version: Literal["25.10.4"] | None
    pipeline_name: Literal["nf-core/rnaseq", "custom-longread-gene-counts"]
    pipeline_version: str
    aligner: Literal["STAR", "minimap2"]
    quantifier: Literal["Salmon", "featureCounts"]
    aggregation: Literal["tximport", "gene_assignment"]
    counts_measure_type: Literal[
        "estimated_counts_unscaled",
        "assigned_longread_gene_counts",
    ]

    @model_validator(mode="after")
    def validate_method_family_contract(self) -> MethodDefinition:
        if self.method_family == "shortread_star_salmon":
            expected = {
                "nextflow_version": "25.10.4",
                "pipeline_name": "nf-core/rnaseq",
                "pipeline_version": "3.26.0",
                "aligner": "STAR",
                "quantifier": "Salmon",
                "aggregation": "tximport",
                "counts_measure_type": "estimated_counts_unscaled",
            }
            for field, value in expected.items():
                if getattr(self, field) != value:
                    raise ValueError(
                        f"shortread_star_salmon requires {field}={value}"
                    )
        elif self.method_family == "longread_gene_counts":
            expected = {
                "pipeline_name": "custom-longread-gene-counts",
                "aligner": "minimap2",
                "quantifier": "featureCounts",
                "aggregation": "gene_assignment",
                "counts_measure_type": "assigned_longread_gene_counts",
            }
            for field, value in expected.items():
                if getattr(self, field) != value:
                    raise ValueError(f"longread_gene_counts requires {field}={value}")
        return self


class ValidationPolicy(StrictDefinitionModel):
    schema_version: Literal["1.0"]
    validation_policy_id: str
    mapping_pass_percent: float
    mapping_fail_below_percent: float
    rrna_warn_percent: float
    mitochondrial_warn_percent: float
    absolute_tolerance: float
    relative_tolerance: float
    qc_metric_aliases: dict[str, list[str]]
