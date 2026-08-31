import json
from pathlib import Path

from rnaseq_mvp.validator import extract_qc_metrics, validate_counts


def _gtf(path: Path) -> Path:
    path.write_text(
        'chr1\tGENCODE\tgene\t1\t10\t.\t+\t.\tgene_id "ENSG000001.1";\n'
        'chr1\tGENCODE\tgene\t20\t30\t.\t+\t.\tgene_id "ENSG000002.2";\n',
        encoding="utf-8",
    )
    return path


def test_counts_rejects_duplicate_gene_and_nan(tmp_path: Path) -> None:
    counts = tmp_path / "counts.tsv"
    counts.write_text(
        "gene_id\tgene_name\tK562_POLYA_REP1\n"
        "ENSG000001.1\tGENE1\t1.5\n"
        "ENSG000001.1\tGENE1\tNaN\n",
        encoding="utf-8",
    )

    report = validate_counts(
        counts,
        ["K562_POLYA_REP1"],
        _gtf(tmp_path / "annotation.gtf"),
    )

    assert report.status == "FAIL"
    assert report.duplicate_gene_id_count == 1
    assert report.nan_value_count == 1


def test_counts_accepts_decimal_estimated_counts(tmp_path: Path) -> None:
    counts = tmp_path / "counts.tsv"
    counts.write_text(
        "gene_id\tgene_name\tS1\tS2\n"
        "ENSG000001.1\tGENE1\t1.5\t0\n"
        "ENSG000002.2\tGENE2\t2.25\t3\n",
        encoding="utf-8",
    )

    report = validate_counts(counts, ["S1", "S2"], _gtf(tmp_path / "a.gtf"))

    assert report.status == "PASS"
    assert report.negative_value_count == 0
    assert report.infinity_value_count == 0
    assert report.unknown_gene_id_count == 0


def test_counts_rejects_column_numeric_and_gene_identity_errors(
    tmp_path: Path,
) -> None:
    counts = tmp_path / "counts.tsv"
    counts.write_text(
        "gene_id\tgene_name\tS1\tEXTRA\n"
        "\tEMPTY\t-1\t0\n"
        "ENSG999999.1\tUNKNOWN\tinf\t2\n",
        encoding="utf-8",
    )

    report = validate_counts(counts, ["S1", "MISSING"], _gtf(tmp_path / "a.gtf"))

    assert report.status == "FAIL"
    assert report.missing_samples == ["MISSING"]
    assert report.extra_samples == ["EXTRA"]
    assert report.empty_gene_id_count == 1
    assert report.negative_value_count == 1
    assert report.infinity_value_count == 1
    assert report.unknown_gene_id_count == 1


def test_qc_thresholds_and_missing_metrics(tmp_path: Path) -> None:
    data_directory = tmp_path / "multiqc_data"
    data_directory.mkdir()
    (data_directory / "multiqc_data.json").write_text(
        json.dumps(
            {
                "report_general_stats_data": [
                    {
                        "PASS_SAMPLE": {
                            "star_percent_uniquely_mapped": 75,
                            "rrna_percent": 2,
                            "mitochondrial_percent": 3,
                            "strandedness": "reverse",
                        },
                        "WARN_SAMPLE": {
                            "star_percent_uniquely_mapped": 60,
                            "rrna_percent": 10,
                            "mitochondrial_percent": 20,
                            "strandedness": "forward",
                        },
                        "FAIL_SAMPLE": {"star_percent_uniquely_mapped": 40},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    aliases = {
        "overall_mapping_percent": ["star_percent_uniquely_mapped"],
        "rrna_percent": ["rrna_percent"],
        "mitochondrial_percent": ["mitochondrial_percent"],
        "strandedness": ["strandedness"],
    }

    metrics = extract_qc_metrics(
        tmp_path,
        ["PASS_SAMPLE", "WARN_SAMPLE", "FAIL_SAMPLE"],
        aliases=aliases,
        mapping_pass_percent=70,
        mapping_fail_below_percent=50,
        rrna_warn_percent=10,
        mitochondrial_warn_percent=20,
    )
    keyed = {(metric.sample_id, metric.metric): metric for metric in metrics}

    assert keyed[("PASS_SAMPLE", "overall_mapping_percent")].status == "PASS"
    assert keyed[("WARN_SAMPLE", "overall_mapping_percent")].status == "WARN"
    assert keyed[("FAIL_SAMPLE", "overall_mapping_percent")].status == "FAIL"
    assert keyed[("WARN_SAMPLE", "rrna_percent")].status == "WARN"
    assert keyed[("WARN_SAMPLE", "mitochondrial_percent")].status == "WARN"
    assert keyed[("WARN_SAMPLE", "strandedness")].status == "WARN"
    assert keyed[("FAIL_SAMPLE", "rrna_percent")].status == "WARN"
    assert keyed[("FAIL_SAMPLE", "rrna_percent")].message == "metric_not_reported"
