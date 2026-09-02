from __future__ import annotations

import csv
import gzip
import json
import math
import re
from pathlib import Path
from typing import Literal, TextIO

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.checksums import hash_file
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.logging_utils import RunLogger
from rnaseq_mvp.manifests import atomic_write_json, write_tsv
from rnaseq_mvp.paths import WorkspacePaths
from rnaseq_mvp.state import RunStatus, StateStore


class ValidationError(RuntimeError):
    """Raised when required validation inputs are unavailable or inconsistent."""


class CountsValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL"]
    row_count: int
    sample_columns: list[str]
    missing_samples: list[str]
    extra_samples: list[str]
    duplicate_gene_id_count: int
    empty_gene_id_count: int
    nan_value_count: int
    infinity_value_count: int
    negative_value_count: int
    unknown_gene_id_count: int
    errors: list[str]


class QcMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    metric: str
    value: float | str | None
    source_key: str | None
    status: Literal["PASS", "WARN", "FAIL"]
    message: str


class ValidationSummaryRow(BaseModel):
    category: str
    item: str
    status: str
    detail: str


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    stage_id: str
    run_id: str
    status: Literal["PASS", "WARN", "FAIL"]
    counts_path: Path
    counts: CountsValidation
    qc_metrics: list[QcMetric]
    reference_traceability: Literal["PASS", "FAIL"]
    required_artifacts: dict[str, str]
    errors: list[str]


_GENE_ID = re.compile(r'(?:^|;)\s*gene_id\s+"([^"]+)"')


def _open_gtf(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _gtf_gene_ids(path: Path) -> set[str]:
    identifiers: set[str] = set()
    with _open_gtf(path) as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[2] != "gene":
                continue
            match = _GENE_ID.search(fields[8])
            if match:
                identifiers.add(match.group(1))
    return identifiers


def validate_counts(
    path: Path,
    expected_samples: list[str],
    gtf_path: Path,
) -> CountsValidation:
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype={"gene_id": "string", "gene_name": "string"},
        keep_default_na=True,
    )
    required_columns = {"gene_id", "gene_name"}
    if not required_columns.issubset(frame.columns):
        missing = sorted(required_columns - set(frame.columns))
        raise ValidationError(f"counts table missing columns: {','.join(missing)}")
    sample_columns = [
        str(column) for column in frame.columns if column not in required_columns
    ]
    missing_samples = [sample for sample in expected_samples if sample not in sample_columns]
    extra_samples = [sample for sample in sample_columns if sample not in expected_samples]

    gene_ids = frame["gene_id"].astype("string")
    empty_mask = gene_ids.isna() | gene_ids.str.strip().eq("")
    nonempty_ids = gene_ids[~empty_mask]
    duplicate_count = int(nonempty_ids.duplicated().sum())
    known_ids = _gtf_gene_ids(gtf_path)
    unknown_count = int((~nonempty_ids.isin(known_ids)).sum())

    numeric = frame[sample_columns].apply(pd.to_numeric, errors="coerce")
    nan_count = int(numeric.isna().sum().sum())
    values = numeric.to_numpy(dtype=float, na_value=float("nan"))
    infinity_count = int(sum(math.isinf(value) for value in values.flat))
    negative_count = int(sum(value < 0 for value in values.flat if math.isfinite(value)))

    errors: list[str] = []
    counters = {
        "missing_sample": len(missing_samples),
        "extra_sample": len(extra_samples),
        "duplicate_gene_id": duplicate_count,
        "empty_gene_id": int(empty_mask.sum()),
        "nan_value": nan_count,
        "infinity_value": infinity_count,
        "negative_value": negative_count,
        "unknown_gene_id": unknown_count,
    }
    errors.extend(name for name, count in counters.items() if count)
    return CountsValidation(
        status="FAIL" if errors else "PASS",
        row_count=len(frame),
        sample_columns=sample_columns,
        missing_samples=missing_samples,
        extra_samples=extra_samples,
        duplicate_gene_id_count=duplicate_count,
        empty_gene_id_count=int(empty_mask.sum()),
        nan_value_count=nan_count,
        infinity_value_count=infinity_count,
        negative_value_count=negative_count,
        unknown_gene_id_count=unknown_count,
        errors=errors,
    )


def _multiqc_path(results_dir: Path) -> Path:
    expected = results_dir / "multiqc_data" / "multiqc_data.json"
    if expected.is_file():
        return expected
    matches = sorted(results_dir.rglob("multiqc_data.json"))
    if len(matches) != 1:
        raise ValidationError(
            "MultiQC data must exist at the expected path or have exactly one fallback match"
        )
    return matches[0]


def _general_stats(payload: dict) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    blocks = payload.get("report_general_stats_data", [])
    if isinstance(blocks, dict):
        blocks = [blocks]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for sample, metrics in block.items():
            if isinstance(metrics, dict):
                merged.setdefault(str(sample), {}).update(metrics)
    return merged


def _metric_value(
    sample_metrics: dict,
    aliases: list[str],
) -> tuple[str | None, object | None]:
    for alias in aliases:
        if alias in sample_metrics:
            return alias, sample_metrics[alias]
    return None, None

def _saved_raw_sample(
    payload: dict,
    section_name: str,
    sample_id: str,
) -> dict:
    raw = payload.get("report_saved_raw_data", {})
    if not isinstance(raw, dict):
        return {}
    section = raw.get(section_name, {})
    if not isinstance(section, dict):
        return {}
    sample = section.get(sample_id, {})
    return sample if isinstance(sample, dict) else {}


def _saved_raw_qc_metrics(
    payload: dict,
    sample_id: str,
) -> dict[str, tuple[str, object]]:
    metrics: dict[str, tuple[str, object]] = {}

    star = _saved_raw_sample(
        payload,
        "multiqc_star",
        sample_id,
    )
    uniquely_mapped = star.get("uniquely_mapped_percent")
    if isinstance(uniquely_mapped, (int, float)):
        metrics["overall_mapping_percent"] = (
            "multiqc_star.uniquely_mapped_percent",
            uniquely_mapped,
        )

    biotypes = _saved_raw_sample(
        payload,
        "multiqc_featurecounts_biotype_plot",
        sample_id,
    )
    numeric_biotypes = {
        str(name): float(value)
        for name, value in biotypes.items()
        if isinstance(value, (int, float))
    }
    total_biotype = sum(numeric_biotypes.values())
    if total_biotype > 0:
        rrna_count = sum(
            value
            for name, value in numeric_biotypes.items()
            if "rrna" in name.lower()
        )
        metrics["rrna_percent"] = (
            "multiqc_featurecounts_biotype_plot.rrna_fraction",
            100 * rrna_count / total_biotype,
        )

    idxstats = _saved_raw_sample(
        payload,
        "multiqc_samtools_idxstats",
        sample_id,
    )
    mapped_by_contig = {
        str(contig): float(values[0])
        for contig, values in idxstats.items()
        if isinstance(values, list)
        and values
        and isinstance(values[0], (int, float))
    }
    total_mapped = sum(mapped_by_contig.values())
    mitochondrial_contig = next(
        (
            contig
            for contig in mapped_by_contig
            if contig.lower() in {"chrm", "mt"}
        ),
        None,
    )
    if mitochondrial_contig is not None and total_mapped > 0:
        metrics["mitochondrial_percent"] = (
            f"multiqc_samtools_idxstats.{mitochondrial_contig}",
            100
            * mapped_by_contig[mitochondrial_contig]
            / total_mapped,
        )

    strand = _saved_raw_sample(
        payload,
        "multiqc_strand_check_summary_table",
        sample_id,
    )
    for key in (
        "rseqc_inferred",
        "provided",
        "salmon_inferred",
    ):
        value = strand.get(key)
        if isinstance(value, str) and value not in {"", "-"}:
            metrics["strandedness"] = (
                f"multiqc_strand_check_summary_table.{key}",
                value,
            )
            break

    return metrics

def extract_qc_metrics(
    results_dir: Path,
    sample_ids: list[str],
    *,
    aliases: dict[str, list[str]],
    mapping_pass_percent: float,
    mapping_fail_below_percent: float,
    rrna_warn_percent: float,
    mitochondrial_warn_percent: float,
) -> list[QcMetric]:
    payload = json.loads(_multiqc_path(results_dir).read_text(encoding="utf-8"))
    stats = _general_stats(payload)
    output: list[QcMetric] = []
    metric_names = (
        "overall_mapping_percent",
        "rrna_percent",
        "mitochondrial_percent",
        "strandedness",
    )
    for sample_id in sample_ids:
        sample_metrics = stats.get(sample_id, {})
        saved_raw_metrics = _saved_raw_qc_metrics(
            payload,
            sample_id,
        )
        for metric in metric_names:
            source_key, raw_value = _metric_value(
                sample_metrics,
                aliases.get(metric, []),
            )
            if source_key is None:
                source_key, raw_value = saved_raw_metrics.get(
                    metric,
                    (None, None),
                )
            if source_key is None:
                output.append(
                    QcMetric(
                        sample_id=sample_id,
                        metric=metric,
                        value=None,
                        source_key=None,
                        status="WARN",
                        message="metric_not_reported",
                    )
                )
                continue
            status: Literal["PASS", "WARN", "FAIL"] = "PASS"
            message = "within_policy"
            value: float | str
            if metric == "strandedness":
                value = str(raw_value)
                if value.lower() != "reverse":
                    status = "WARN"
                    message = "expected_reverse_strandedness"
            else:
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    value = str(raw_value)
                    status = "WARN"
                    message = "metric_not_numeric"
                else:
                    if metric == "overall_mapping_percent":
                        if value < mapping_fail_below_percent:
                            status = "FAIL"
                            message = "below_fail_threshold"
                        elif value < mapping_pass_percent:
                            status = "WARN"
                            message = "below_pass_threshold"
                    elif metric == "rrna_percent" and value >= rrna_warn_percent or (
                        metric == "mitochondrial_percent"
                        and value >= mitochondrial_warn_percent
                    ):
                        status = "WARN"
                        message = "at_or_above_warning_threshold"
            output.append(
                QcMetric(
                    sample_id=sample_id,
                    metric=metric,
                    value=value,
                    source_key=source_key,
                    status=status,
                    message=message,
                )
            )
    return output


def _reference_is_traced(reference_manifest: Path, gtf_path: Path) -> bool:
    with reference_manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    matches = [row for row in rows if row.get("role") == "annotation_gtf"]
    if len(matches) != 1:
        return False
    row = matches[0]
    return (
        Path(row["path"]).resolve() == gtf_path.resolve()
        and gtf_path.is_file()
        and hash_file(gtf_path, "sha256") == row.get("sha256")
    )


def validate_stage(
    stage_id: str,
    run_id: str,
    workspace: Path,
    registry: DefinitionRegistry,
) -> ValidationReport:
    paths = WorkspacePaths.from_root(workspace)
    run_directory = paths.runs / run_id
    state_store = StateStore(paths.root)
    state = state_store.load(run_id)
    if state.stage_id != stage_id or state.status != RunStatus.EXECUTED:
        raise ValidationError("validation requires the matching EXECUTED run")
    stage = registry.stage(stage_id)
    dataset = registry.dataset(stage.dataset_id)
    policy = registry.validation(stage.validation_policy_id)
    parameters = yaml.safe_load(
        (run_directory / "parameters.yaml").read_text(encoding="utf-8")
    )
    results_dir = Path(parameters["outdir"])
    counts_path = results_dir / "star_salmon" / "salmon.merged.gene_counts.tsv"
    required = {
        "counts": counts_path,
        "tpm": results_dir / "star_salmon" / "salmon.merged.gene_tpm.tsv",
        "lengths": results_dir / "star_salmon" / "salmon.merged.gene_lengths.tsv",
        "multiqc_report": results_dir
        / "multiqc"
        / "star_salmon"
        / "multiqc_report.html",
        "multiqc_data": results_dir
        / "multiqc"
        / "star_salmon"
        / "multiqc_report_data"
        / "multiqc_data.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ValidationError(f"required result artifacts missing: {','.join(missing)}")
    gtf_path = Path(parameters["gtf"])
    expected_samples = [
        sample_id for sample_id in stage.sample_ids if sample_id in dataset.sample_ids
    ] if hasattr(dataset, "sample_ids") else stage.sample_ids
    counts = validate_counts(counts_path, expected_samples, gtf_path)
    multiqc_root = required["multiqc_report"].parent
    qc_metrics = extract_qc_metrics(
        multiqc_root,
        expected_samples,
        aliases=policy.qc_metric_aliases,
        mapping_pass_percent=policy.mapping_pass_percent,
        mapping_fail_below_percent=policy.mapping_fail_below_percent,
        rrna_warn_percent=policy.rrna_warn_percent,
        mitochondrial_warn_percent=policy.mitochondrial_warn_percent,
    )
    reference_traceability = (
        "PASS"
        if _reference_is_traced(run_directory / "reference_manifest.tsv", gtf_path)
        else "FAIL"
    )
    errors: list[str] = []
    if counts.status == "FAIL":
        errors.extend(counts.errors)
    if reference_traceability == "FAIL":
        errors.append("reference_traceability")
    if any(metric.status == "FAIL" for metric in qc_metrics):
        errors.append("qc_fail")
    if errors:
        status: Literal["PASS", "WARN", "FAIL"] = "FAIL"
    elif any(metric.status == "WARN" for metric in qc_metrics):
        status = "WARN"
    else:
        status = "PASS"
    report = ValidationReport(
        stage_id=stage_id,
        run_id=run_id,
        status=status,
        counts_path=counts_path,
        counts=counts,
        qc_metrics=qc_metrics,
        reference_traceability=reference_traceability,
        required_artifacts={name: str(path) for name, path in required.items()},
        errors=sorted(set(errors)),
    )
    atomic_write_json(
        run_directory / "validation_report.json", report.model_dump(mode="json")
    )
    write_tsv(run_directory / "qc_metrics.tsv", qc_metrics)
    summary_rows = [
        ValidationSummaryRow(
            category="counts",
            item="gene_counts",
            status=counts.status,
            detail=",".join(counts.errors) or "valid",
        ),
        ValidationSummaryRow(
            category="reference",
            item="annotation_gtf",
            status=reference_traceability,
            detail=str(gtf_path),
        ),
        ValidationSummaryRow(
            category="overall",
            item="validation",
            status=status,
            detail=",".join(report.errors) or "valid",
        ),
    ]
    write_tsv(run_directory / "validation_summary.tsv", summary_rows)
    if status == "PASS":
        state_store.transition(run_id, RunStatus.VALIDATED_PASS)
        state_store.transition(run_id, RunStatus.AWAITING_REVIEW)
    elif status == "WARN":
        state_store.transition(run_id, RunStatus.VALIDATED_WITH_WARNINGS)
        state_store.transition(run_id, RunStatus.AWAITING_REVIEW)
    else:
        state_store.transition(run_id, RunStatus.VALIDATION_FAILED)
    RunLogger(run_directory, run_id).event(
        "validate", "scientific_validation_completed", status
    )
    return report
