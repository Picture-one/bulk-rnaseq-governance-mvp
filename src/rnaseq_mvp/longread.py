from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class LongreadPostprocessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results_dir: Path
    sample_ids: list[str]
    gene_rows: list[dict[str, str | int | float]]
    alignment_rows: list[dict[str, str | int | float]]
    qc_rows: list[dict[str, str | int | float]]
    provenance: dict[str, str | int | float | bool | None]


class LongreadPostprocessOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts_path: Path
    alignment_summary_path: Path
    qc_metrics_path: Path
    provenance_path: Path


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_tsv(path: Path, rows: list[dict[str, str | int | float]], columns: list[str]) -> None:
    with path.parent.joinpath(f"{path.name}.tmp").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(path.parent / f"{path.name}.tmp", path)


def write_longread_postprocess_outputs(
    payload: LongreadPostprocessInput,
) -> LongreadPostprocessOutput:
    longread_dir = payload.results_dir / "longread"
    longread_dir.mkdir(parents=True, exist_ok=True)

    counts_path = longread_dir / "gene_counts_raw.tsv"
    alignment_summary_path = longread_dir / "alignment_summary.tsv"
    qc_metrics_path = longread_dir / "longread_qc_metrics.tsv"
    provenance_path = longread_dir / "provenance.json"

    count_columns = ["gene_id", "gene_name", *payload.sample_ids]
    _write_tsv(counts_path, payload.gene_rows, count_columns)
    _write_tsv(alignment_summary_path, payload.alignment_rows, list(payload.alignment_rows[0]))
    _write_tsv(qc_metrics_path, payload.qc_rows, list(payload.qc_rows[0]))
    _atomic_write_text(
        provenance_path,
        f"{json.dumps(payload.provenance, ensure_ascii=False, indent=2, sort_keys=True)}\n",
    )

    return LongreadPostprocessOutput(
        counts_path=counts_path,
        alignment_summary_path=alignment_summary_path,
        qc_metrics_path=qc_metrics_path,
        provenance_path=provenance_path,
    )
