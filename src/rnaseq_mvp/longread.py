from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Protocol

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


class LongreadCommandExecutor(Protocol):
    def run(self, command: list[str], stdout_path: Path | None = None) -> None: ...


class RealLongreadCommandExecutor:
    def run(self, command: list[str], stdout_path: Path | None = None) -> None:
        if stdout_path is None:
            subprocess.run(command, check=True)
            return
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("w", encoding="utf-8") as handle:
            subprocess.run(command, check=True, stdout=handle)


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


def _read_samplesheet(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "sample",
        "input_file",
        "platform",
        "protocol",
        "strandedness",
        "reference_profile_id",
    }
    if not rows:
        raise ValueError("long-read samplesheet must contain at least one sample")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"long-read samplesheet missing columns: {','.join(sorted(missing))}")
    for row in rows:
        if row["platform"] != "ONT":
            raise ValueError("long-read v1 supports ONT only")
        if row["protocol"] not in {"cDNA", "direct RNA"}:
            raise ValueError("long-read v1 requires cDNA or direct RNA protocol")
    return rows


def _gene_names_from_gtf(path: Path) -> dict[str, str]:
    gene_id_pattern = re.compile(r'(?:^|;)\s*gene_id\s+"([^"]+)"')
    gene_name_pattern = re.compile(r'(?:^|;)\s*gene_name\s+"([^"]+)"')
    names: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[2] != "gene":
                continue
            gene_id = gene_id_pattern.search(fields[8])
            if gene_id is None:
                continue
            gene_name = gene_name_pattern.search(fields[8])
            names[gene_id.group(1)] = gene_name.group(1) if gene_name else gene_id.group(1)
    return names


def _parse_featurecounts(
    path: Path,
    sample_id: str,
    gene_names: dict[str, str],
) -> list[dict[str, str | int]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    reader = csv.DictReader(lines, delimiter="\t")
    rows: list[dict[str, str | int]] = []
    for row in reader:
        gene_id = row["Geneid"]
        count_column = next(column for column in row if column.endswith(".bam"))
        rows.append(
            {
                "gene_id": gene_id,
                "gene_name": gene_names.get(gene_id, gene_id),
                sample_id: int(row[count_column]),
            }
        )
    return rows


def _parse_seqkit_stats(path: Path, sample_id: str) -> list[dict[str, str | int | float]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    return [
        {"sample_id": sample_id, "metric": "total_reads", "value": int(row["num_seqs"])},
        {"sample_id": sample_id, "metric": "total_bases", "value": int(row["sum_len"])},
        {"sample_id": sample_id, "metric": "mean_read_length", "value": float(row["avg_len"])},
        {"sample_id": sample_id, "metric": "max_read_length", "value": int(row["max_len"])},
    ]


def _parse_alignment_rate(path: Path) -> float:
    pattern = re.compile(r"\((\d+(?:\.\d+)?)%")
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if " mapped " in line:
                match = pattern.search(line)
                if match:
                    return float(match.group(1))
    return 0.0


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


def run_longread_workflow(
    *,
    samplesheet: Path,
    fasta: Path,
    gtf: Path,
    outdir: Path,
    threads: int,
    executor: LongreadCommandExecutor | None = None,
) -> LongreadPostprocessOutput:
    executor = executor or RealLongreadCommandExecutor()
    samples = _read_samplesheet(samplesheet)
    if len(samples) != 1:
        raise ValueError("long-read MVP smoke workflow currently supports one sample")
    sample = samples[0]
    sample_id = sample["sample"]
    fastq = Path(sample["input_file"])
    workdir = outdir / "longread" / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    seqkit_stats = workdir / f"{sample_id}.seqkit.tsv"
    sam_path = workdir / f"{sample_id}.sam"
    bam_path = workdir / f"{sample_id}.sorted.bam"
    flagstat_path = workdir / f"{sample_id}.flagstat.txt"
    featurecounts_path = workdir / "featurecounts.gene_counts.txt"

    executor.run(["seqkit", "stats", "-T", str(fastq)], stdout_path=seqkit_stats)
    minimap2_command = ["minimap2", "-ax", "splice"]
    if sample["protocol"] == "direct RNA":
        minimap2_command.extend(["-uf", "-k14"])
    minimap2_command.extend(["-t", str(threads), str(fasta), str(fastq)])
    executor.run(minimap2_command, stdout_path=sam_path)
    executor.run(["samtools", "sort", "-@", str(threads), "-o", str(bam_path), str(sam_path)])
    executor.run(["samtools", "index", str(bam_path)])
    executor.run(["samtools", "flagstat", str(bam_path)], stdout_path=flagstat_path)
    executor.run(
        [
            "featureCounts",
            "-T",
            str(threads),
            "-L",
            "-t",
            "exon",
            "-g",
            "gene_id",
            "-a",
            str(gtf),
            "-o",
            str(featurecounts_path),
            str(bam_path),
        ]
    )

    gene_rows = _parse_featurecounts(featurecounts_path, sample_id, _gene_names_from_gtf(gtf))
    alignment_rate = _parse_alignment_rate(flagstat_path)
    alignment_rows = [
        {
            "sample_id": sample_id,
            "alignment_rate": alignment_rate,
            "primary_alignment_rate": alignment_rate,
        }
    ]
    qc_rows = _parse_seqkit_stats(seqkit_stats, sample_id)
    qc_rows.append(
        {
            "sample_id": sample_id,
            "metric": "alignment_rate",
            "value": alignment_rate,
        }
    )
    provenance = {
        "method_profile_id": "longread_rnaseq_minimap2_gene_counts_v1",
        "measure_type": "assigned_longread_gene_counts",
        "reference_profile_id": sample["reference_profile_id"],
        "aligner": "minimap2",
        "quantifier": "featureCounts",
        "threads": threads,
    }
    return write_longread_postprocess_outputs(
        LongreadPostprocessInput(
            results_dir=outdir,
            sample_ids=[sample_id],
            gene_rows=gene_rows,
            alignment_rows=alignment_rows,
            qc_rows=qc_rows,
            provenance=provenance,
        )
    )
