import json
from pathlib import Path

import pytest

from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.packager import PackageError, package_run
from rnaseq_mvp.state import RunStatus, StateStore


def test_package_requires_review_acceptance(tmp_path: Path) -> None:
    run_id = "T2A_20260901T013000Z"
    store = StateStore(tmp_path)
    store.create("T2A", run_id)
    store.transition(run_id, RunStatus.PREFLIGHT_PASSED)
    store.transition(run_id, RunStatus.PREPARED)

    repo_root = Path(__file__).resolve().parents[2]
    registry = DefinitionRegistry.load(repo_root / "definitions")
    with pytest.raises(PackageError, match="REVIEW_ACCEPTED"):
        package_run("T2A", run_id, tmp_path, registry)


def test_package_contains_governed_assets_without_changing_counts(
    tmp_path: Path,
) -> None:
    run_id = "T2A_20260901T013000Z"
    run_directory = tmp_path / "runs" / run_id
    run_directory.mkdir(parents=True)
    results = tmp_path / "results" / "T2A" / run_id
    star = results / "star_salmon"
    multiqc = results / "multiqc" / "star_salmon"
    pipeline = results / "pipeline_info"
    star.mkdir(parents=True)
    multiqc.mkdir(parents=True)
    pipeline.mkdir(parents=True)
    counts_content = "gene_id\tgene_name\tK562_POLYA_REP1\nENSG1\tG1\t1.5\n"
    for name, content in {
        "salmon.merged.gene_counts.tsv": counts_content,
        "salmon.merged.gene_tpm.tsv": "gene_id\tK562_POLYA_REP1\nENSG1\t2.0\n",
        "salmon.merged.gene_lengths.tsv": "gene_id\tK562_POLYA_REP1\nENSG1\t100\n",
    }.items():
        (star / name).write_text(content, encoding="utf-8")
    (multiqc / "multiqc_report.html").write_text("<html></html>", encoding="utf-8")
    (pipeline / "software_versions.yml").write_text("STAR: 2.7\n", encoding="utf-8")
    for name in (
        "input_manifest.tsv",
        "reference_manifest.tsv",
        "samplesheet.csv",
        "validation_report.json",
        "review_record.json",
        "run_provenance.json",
    ):
        (run_directory / name).write_text(f"{name}\n", encoding="utf-8")
    (run_directory / "parameters.yaml").write_text(
        f"outdir: {results.resolve()}\n", encoding="utf-8"
    )
    (run_directory / "validation_report.json").write_text(
        json.dumps({"status": "PASS"}), encoding="utf-8"
    )
    (run_directory / "review_record.json").write_text(
        json.dumps({"decision": "accept"}), encoding="utf-8"
    )
    store = StateStore(tmp_path)
    store.create("T2A", run_id)
    for status in (
        RunStatus.PREFLIGHT_PASSED,
        RunStatus.PREPARED,
        RunStatus.RUNNING,
        RunStatus.EXECUTED,
        RunStatus.VALIDATED_PASS,
        RunStatus.AWAITING_REVIEW,
        RunStatus.REVIEW_ACCEPTED,
    ):
        store.transition(run_id, status)
    repo_root = Path(__file__).resolve().parents[2]
    registry = DefinitionRegistry.load(repo_root / "definitions")

    result = package_run("T2A", run_id, tmp_path, registry)

    expected = {
        "gene_counts_raw_estimated.tsv",
        "gene_counts_raw_estimated.metadata.json",
        "gene_tpm.tsv",
        "gene_lengths.tsv",
        "multiqc_report.html",
        "input_manifest.tsv",
        "reference_manifest.tsv",
        "samplesheet.csv",
        "parameters.yaml",
        "validation_report.json",
        "review_record.json",
        "software_versions.yml",
        "run_provenance.json",
        "README.txt",
        "checksums.sha256",
    }
    assert {path.name for path in result.release_directory.iterdir()} == expected
    assert (
        result.release_directory / "gene_counts_raw_estimated.tsv"
    ).read_text(encoding="utf-8") == counts_content
    checksum_lines = (result.release_directory / "checksums.sha256").read_text(
        encoding="utf-8"
    ).splitlines()
    assert checksum_lines == sorted(checksum_lines)
    assert all("checksums.sha256" not in line for line in checksum_lines)
    assert store.load(run_id).status == RunStatus.PACKAGED
