import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from rnaseq_mvp.definitions import DefinitionRegistry
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
from rnaseq_mvp.prepare import PreparationError, prepare_stage


def _md5(payload: bytes) -> str:
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def _registry(payloads: dict[str, bytes]) -> DefinitionRegistry:
    files = [
        FileDefinition(
            role="R1",
            file_accession="TEST_R1",
            filename="TEST_R1.fastq.gz",
            url="https://example.org/TEST_R1.fastq.gz",
            expected_bytes=len(payloads["TEST_R1.fastq.gz"]),
            expected_md5=_md5(payloads["TEST_R1.fastq.gz"]),
        ),
        FileDefinition(
            role="R2",
            file_accession="TEST_R2",
            filename="TEST_R2.fastq.gz",
            url="https://example.org/TEST_R2.fastq.gz",
            expected_bytes=len(payloads["TEST_R2.fastq.gz"]),
            expected_md5=_md5(payloads["TEST_R2.fastq.gz"]),
        ),
    ]
    dataset = DatasetDefinition(
        schema_version="1.0",
        dataset_id="TEST_DATASET",
        source_database="ENCODE",
        experiment_accession="TESTEXP",
        organism="Homo sapiens",
        biosample="K562",
        assay="polyA plus RNA-seq",
        library_selection="Poly(A)+",
        read_layout="paired-end",
        read_length=101,
        strandedness="reverse",
        sequencing_platform="Illumina",
        samples=[
            SampleDefinition(
                sample_id="TEST_SAMPLE",
                biological_replicate=1,
                biosample_accession="TESTBIO",
                library_accession="TESTLIB",
                files=files,
            )
        ],
    )
    reference = ReferenceDefinition(
        schema_version="1.0",
        reference_profile_id="TEST_REFERENCE",
        organism="Homo sapiens",
        genome_build="GRCh38",
        assembly_patch="p14",
        annotation_provider="GENCODE",
        annotation_release="50",
        assembly_scope="primary_assembly",
        files=[
            ReferenceFileDefinition(
                role="genome_fasta",
                filename="genome.fa.gz",
                url="https://example.org/genome.fa.gz",
                expected_bytes=len(payloads["genome.fa.gz"]),
                expected_md5=_md5(payloads["genome.fa.gz"]),
            ),
            ReferenceFileDefinition(
                role="annotation_gtf",
                filename="annotation.gtf.gz",
                url="https://example.org/annotation.gtf.gz",
                expected_bytes=len(payloads["annotation.gtf.gz"]),
                expected_md5=_md5(payloads["annotation.gtf.gz"]),
            ),
        ],
    )
    stage = StageDefinition(
        schema_version="1.0",
        stage_id="T2A",
        dataset_id=dataset.dataset_id,
        sample_ids=["TEST_SAMPLE"],
        reference_profile_id=reference.reference_profile_id,
        method_profile_id="TEST_METHOD",
        validation_policy_id="TEST_POLICY",
        expected_outputs=["gene_counts_raw_estimated"],
    )
    method = MethodDefinition(
        schema_version="1.0",
        method_profile_id="TEST_METHOD",
        nextflow_version="25.10.4",
        pipeline_name="nf-core/rnaseq",
        pipeline_version="3.26.0",
        aligner="STAR",
        quantifier="Salmon",
        aggregation="tximport",
        counts_measure_type="estimated_counts_unscaled",
    )
    policy = ValidationPolicy(
        schema_version="1.0",
        validation_policy_id="TEST_POLICY",
        mapping_pass_percent=70,
        mapping_fail_below_percent=50,
        rrna_warn_percent=10,
        mitochondrial_warn_percent=20,
        absolute_tolerance=1e-6,
        relative_tolerance=1e-8,
        qc_metric_aliases={},
    )
    return DefinitionRegistry(
        stages={stage.stage_id: stage},
        datasets={dataset.dataset_id: dataset},
        references={reference.reference_profile_id: reference},
        methods={method.method_profile_id: method},
        validations={policy.validation_policy_id: policy},
    )


def test_prepare_is_idempotent_for_verified_files(tmp_path: Path) -> None:
    fixed_now = datetime(2026, 9, 1, 1, 30, tzinfo=timezone.utc)
    payloads = {
        "TEST_R1.fastq.gz": gzip.compress(b"@r1\nAC\n+\nII\n", mtime=0),
        "TEST_R2.fastq.gz": gzip.compress(b"@r1\nGT\n+\nII\n", mtime=0),
        "genome.fa.gz": gzip.compress(b">chr1\nACGT\n", mtime=0),
        "annotation.gtf.gz": gzip.compress(
            b'chr1\ttest\tgene\t1\t4\t.\t+\t.\tgene_id "G1";\n', mtime=0
        ),
    }
    registry = _registry(payloads)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "preflight_report.json").write_text(
        json.dumps(
            {
                "profile": "server_docker",
                "workspace": str(tmp_path.resolve()),
                "status": "PASS",
                "created_at": fixed_now.isoformat(),
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, content=payloads[Path(request.url.path).name])

    client = httpx.Client(transport=httpx.MockTransport(handler))

    first = prepare_stage("T2A", tmp_path, registry, client, fixed_now)
    second = prepare_stage("T2A", tmp_path, registry, client, fixed_now)

    assert first.status == "PREPARED"
    assert second.status == "PREPARED"
    assert request_count == 4
    assert first.run_id == "T2A_20260901T013000Z"
    assert first.input_manifest_sha256 == second.input_manifest_sha256
    assert Path(first.samplesheet_path).is_file()
    assert Path(first.parameters_path).is_file()


def test_prepare_quarantines_invalid_download(tmp_path: Path) -> None:
    fixed_now = datetime(2026, 9, 1, 1, 30, tzinfo=timezone.utc)
    payloads = {
        "TEST_R1.fastq.gz": gzip.compress(b"@r1\nAC\n+\nII\n", mtime=0),
        "TEST_R2.fastq.gz": gzip.compress(b"@r1\nGT\n+\nII\n", mtime=0),
        "genome.fa.gz": gzip.compress(b">chr1\nACGT\n", mtime=0),
        "annotation.gtf.gz": gzip.compress(b"gtf\n", mtime=0),
    }
    registry = _registry(payloads)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "preflight_report.json").write_text(
        json.dumps(
            {
                "profile": "server_docker",
                "workspace": str(tmp_path.resolve()),
                "status": "PASS",
                "created_at": fixed_now.isoformat(),
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        filename = Path(request.url.path).name
        content = b"invalid" if filename == "TEST_R1.fastq.gz" else payloads[filename]
        return httpx.Response(200, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(PreparationError, match="verification failed"):
        prepare_stage("T2A", tmp_path, registry, client, fixed_now)

    quarantined = list((tmp_path / "quarantine" / "downloads").glob("*.invalid"))
    assert len(quarantined) == 1
    assert quarantined[0].name.startswith("TEST_R1.fastq.gz.")
