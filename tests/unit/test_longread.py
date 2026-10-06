import json
from pathlib import Path

from rnaseq_mvp.longread import LongreadPostprocessInput, write_longread_postprocess_outputs


def test_write_longread_postprocess_outputs(tmp_path: Path) -> None:
    output = write_longread_postprocess_outputs(
        LongreadPostprocessInput(
            results_dir=tmp_path,
            sample_ids=["LONG_SAMPLE"],
            gene_rows=[
                {
                    "gene_id": "ENSG000001.1",
                    "gene_name": "GENE1",
                    "LONG_SAMPLE": 12,
                }
            ],
            alignment_rows=[
                {
                    "sample_id": "LONG_SAMPLE",
                    "alignment_rate": 88.5,
                    "primary_alignment_rate": 86.0,
                }
            ],
            qc_rows=[
                {
                    "sample_id": "LONG_SAMPLE",
                    "metric": "total_reads",
                    "value": 1000,
                }
            ],
            provenance={
                "method_profile_id": "longread_rnaseq_minimap2_gene_counts_v1",
                "measure_type": "assigned_longread_gene_counts",
            },
        )
    )

    assert output.counts_path == tmp_path / "longread" / "gene_counts_raw.tsv"
    assert output.alignment_summary_path.is_file()
    assert output.qc_metrics_path.is_file()
    assert output.provenance_path.is_file()
    assert output.counts_path.read_text(encoding="utf-8").splitlines() == [
        "gene_id\tgene_name\tLONG_SAMPLE",
        "ENSG000001.1\tGENE1\t12",
    ]
    provenance = json.loads(output.provenance_path.read_text(encoding="utf-8"))
    assert provenance["measure_type"] == "assigned_longread_gene_counts"
