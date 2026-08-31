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


class FileDefinition(StrictDefinitionModel):
    role: Literal["R1", "R2"]
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

    @model_validator(mode="after")
    def validate_read_pair(self) -> SampleDefinition:
        roles = [file.role for file in self.files]

        if len(roles) != 2 or roles.count("R1") != 1 or roles.count("R2") != 1:
            raise ValueError("sample must contain exactly one R1 and one R2")

        return self


class DatasetDefinition(StrictDefinitionModel):
    schema_version: Literal["1.0"]
    dataset_id: str
    source_database: Literal["ENCODE"]
    experiment_accession: str
    organism: Literal["Homo sapiens"]
    biosample: str
    assay: Literal["polyA plus RNA-seq"]
    library_selection: Literal["Poly(A)+"]
    read_layout: Literal["paired-end"]
    read_length: PositiveInt
    strandedness: Literal["reverse"]
    sequencing_platform: str
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
    nextflow_version: Literal["25.10.4"]
    pipeline_name: Literal["nf-core/rnaseq"]
    pipeline_version: Literal["3.26.0"]
    aligner: Literal["STAR"]
    quantifier: Literal["Salmon"]
    aggregation: Literal["tximport"]
    counts_measure_type: Literal["estimated_counts_unscaled"]


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
