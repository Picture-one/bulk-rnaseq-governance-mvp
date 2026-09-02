import json
from pathlib import Path

from rnaseq_mvp.checksums import hash_file
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.state import RunStatus, StateStore
from rnaseq_mvp.validator import validate_stage


def test_validate_and_revalidate_stage_preserves_history(tmp_path: Path) -> None:
    run_id = "T2A_20260901T013000Z"
    run_directory = tmp_path / "runs" / run_id
    run_directory.mkdir(parents=True)
    results = tmp_path / "results" / "T2A" / run_id
    star = results / "star_salmon"
    multiqc = results / "multiqc" / "star_salmon"
    data = multiqc / "multiqc_report_data"
    star.mkdir(parents=True)
    data.mkdir(parents=True)
    counts = (
        "gene_id\tgene_name\tK562_POLYA_REP1\n"
        "ENSG000001.1\tGENE1\t1.5\n"
    )
    (star / "salmon.merged.gene_counts.tsv").write_text(counts, encoding="utf-8")
    (star / "salmon.merged.gene_tpm.tsv").write_text(counts, encoding="utf-8")
    (star / "salmon.merged.gene_lengths.tsv").write_text(counts, encoding="utf-8")
    (multiqc / "multiqc_report.html").write_text("<html></html>", encoding="utf-8")
    (data / "multiqc_data.json").write_text(
        json.dumps(
            {
                "report_general_stats_data": [
                    {
                        "K562_POLYA_REP1": {
                            "star_percent_uniquely_mapped": 80,
                            "rrna_percent": 2,
                            "mitochondrial_percent": 3,
                            "strandedness": "reverse",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    gtf = tmp_path / "reference" / "test" / "annotation.gtf"
    gtf.parent.mkdir(parents=True)
    gtf.write_text(
        'chr1\tGENCODE\tgene\t1\t10\t.\t+\t.\tgene_id "ENSG000001.1";\n',
        encoding="utf-8",
    )
    (run_directory / "reference_manifest.tsv").write_text(
        "role\tfilename\tpath\texpected_bytes\tobserved_bytes\t"
        "expected_md5\tobserved_md5\tsha256\n"
        f"annotation_gtf\tannotation.gtf\t{gtf.resolve()}\t1\t1\tx\tx\t"
        f"{hash_file(gtf, 'sha256')}\n",
        encoding="utf-8",
    )
    (run_directory / "parameters.yaml").write_text(
        f"outdir: {results.resolve()}\ngtf: {gtf.resolve()}\n",
        encoding="utf-8",
    )
    store = StateStore(tmp_path)
    store.create("T2A", run_id)
    store.transition(run_id, RunStatus.PREFLIGHT_PASSED)
    store.transition(run_id, RunStatus.PREPARED)
    store.transition(run_id, RunStatus.RUNNING)
    store.transition(run_id, RunStatus.EXECUTED)
    repo_root = Path(__file__).resolve().parents[2]
    registry = DefinitionRegistry.load(repo_root / "definitions")

    report = validate_stage("T2A", run_id, tmp_path, registry)

    assert report.status == "PASS"
    assert (run_directory / "validation_report.json").is_file()
    assert (run_directory / "validation_summary.tsv").is_file()
    assert (run_directory / "qc_metrics.tsv").is_file()
    assert store.load(run_id).status == RunStatus.AWAITING_REVIEW
    report_path = run_directory / "validation_report.json"
    previous_report = report_path.read_text(encoding="utf-8")

    revalidated = validate_stage(
        "T2A",
        run_id,
        tmp_path,
        registry,
        revalidate=True,
        reason="MultiQC 3.26 parser compatibility fix",
    )

    assert revalidated.status == "PASS"
    assert store.load(run_id).status == RunStatus.AWAITING_REVIEW

    history_root = run_directory / "validation_history"
    history_directories = sorted(
        path for path in history_root.iterdir() if path.is_dir()
    )
    assert len(history_directories) == 1

    archived = history_directories[0]
    assert (
        archived / "validation_report.json"
    ).read_text(encoding="utf-8") == previous_report
    assert (archived / "qc_metrics.tsv").is_file()
    assert (archived / "validation_summary.tsv").is_file()
    assert (
        archived / "revalidation_reason.txt"
    ).read_text(encoding="utf-8") == (
        "MultiQC 3.26 parser compatibility fix\n"
    )
    invalid_counts = (
        "gene_id\tgene_name\tK562_POLYA_REP1\n"
        "ENSG000001.1\tGENE1\t-1\n"
    )
    (
        star / "salmon.merged.gene_counts.tsv"
    ).write_text(
        invalid_counts,
        encoding="utf-8",
    )

    failed_revalidation = validate_stage(
        "T2A",
        run_id,
        tmp_path,
        registry,
        revalidate=True,
        reason="Test failed revalidation handling",
    )

    assert failed_revalidation.status == "FAIL"
    assert (
        store.load(run_id).status
        == RunStatus.VALIDATION_FAILED
    )

    history_directories = sorted(
        path
        for path in history_root.iterdir()
        if path.is_dir()
    )
    assert len(history_directories) == 2
