from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.checksums import FileVerification, hash_file, verify_expected_file
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.downloader import download_to_part
from rnaseq_mvp.logging_utils import RunLogger
from rnaseq_mvp.manifests import atomic_write_json, manifest_sha256, write_tsv
from rnaseq_mvp.paths import WorkspacePaths
from rnaseq_mvp.state import RunStatus, StateStore, new_run_id


class PreparationError(RuntimeError):
    """Raised when governed inputs cannot be prepared."""


class InputManifestRow(BaseModel):
    sample_id: str
    biological_replicate: int
    role: str
    file_accession: str
    filename: str
    path: str
    expected_bytes: int
    observed_bytes: int
    expected_md5: str
    observed_md5: str
    sha256: str


class ReferenceManifestRow(BaseModel):
    role: str
    filename: str
    path: str
    expected_bytes: int
    observed_bytes: int
    expected_md5: str
    observed_md5: str
    sha256: str


class PreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PREPARED"]
    stage_id: str
    run_id: str
    input_manifest_path: Path
    reference_manifest_path: Path
    samplesheet_path: Path
    parameters_path: Path
    input_manifest_sha256: str
    reference_manifest_sha256: str
    samplesheet_sha256: str
    scientific_template_sha256: str
    parameters_sha256: str


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


def _require_recent_preflight(workspace: Path, now: datetime) -> None:
    report_path = workspace / "reports" / "preflight_report.json"
    if not report_path.is_file():
        raise PreparationError("a PASS preflight report is required")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise PreparationError("preflight report is not PASS")
    if Path(report.get("workspace", "")).resolve() != workspace.resolve():
        raise PreparationError("preflight report belongs to a different workspace")
    created_at = datetime.fromisoformat(str(report["created_at"]).replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        raise PreparationError("preflight timestamp must be timezone-aware")
    if now.astimezone(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(
        hours=24
    ):
        raise PreparationError("preflight report is older than 24 hours")


def _quarantine(
    source: Path,
    paths: WorkspacePaths,
    now: datetime,
) -> Path:
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = paths.quarantine / "downloads" / f"{source.name}.{timestamp}.invalid"
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    return target


def _verified_file(
    *,
    url: str,
    destination: Path,
    expected_bytes: int,
    expected_md5: str,
    client: httpx.Client,
    paths: WorkspacePaths,
    now: datetime,
) -> FileVerification:
    if destination.exists():
        verification = verify_expected_file(
            destination, expected_bytes, expected_md5, gzip_required=True
        )
        if verification.valid:
            return verification
        _quarantine(destination, paths, now)

    result = download_to_part(url, destination, client, expected_bytes)
    verification = verify_expected_file(
        result.part_path, expected_bytes, expected_md5, gzip_required=True
    )
    if not verification.valid:
        quarantined = _quarantine(result.part_path, paths, now)
        raise PreparationError(
            f"file verification failed for {destination.name}: "
            f"{','.join(verification.errors)}; quarantined={quarantined}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(result.part_path, destination)
    return verify_expected_file(
        destination, expected_bytes, expected_md5, gzip_required=True
    )


def _write_samplesheet(path: Path, rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO(newline="")
    columns = [
        "sample",
        "fastq_1",
        "fastq_2",
        "strandedness",
        "seq_platform",
        "seq_center",
    ]
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _atomic_write_text(path, buffer.getvalue())


def prepare_stage(
    stage_id: str,
    workspace: Path,
    registry: DefinitionRegistry,
    client: httpx.Client,
    now: datetime,
) -> PreparationResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("prepare timestamp must be timezone-aware")
    paths = WorkspacePaths.from_root(workspace)
    _require_recent_preflight(paths.root, now)

    try:
        stage = registry.stage(stage_id)
        dataset = registry.dataset(stage.dataset_id)
        reference = registry.reference(stage.reference_profile_id)
        registry.method(stage.method_profile_id)
        registry.validation(stage.validation_policy_id)
    except KeyError as error:
        raise ValueError(f"unknown scientific definition: {error.args[0]}") from error

    run_id = new_run_id(stage_id, now)
    store = StateStore(paths.root)
    state_path = paths.runs / run_id / "state.json"
    if state_path.exists():
        state = store.load(run_id)
        if state.status != RunStatus.PREPARED:
            raise PreparationError(f"run cannot be resumed from state {state.status.value}")
    else:
        state = store.create(stage_id, run_id)
        state = store.transition(state.run_id, RunStatus.PREFLIGHT_PASSED)

    run_directory = paths.runs / run_id
    logger = RunLogger(run_directory, run_id)
    selected_samples = [
        sample for sample in dataset.samples if sample.sample_id in stage.sample_ids
    ]
    if [sample.sample_id for sample in selected_samples] != stage.sample_ids:
        raise PreparationError("stage sample order or membership is invalid")

    input_rows: list[InputManifestRow] = []
    sample_paths: dict[str, dict[str, Path]] = {}
    for sample in selected_samples:
        roles = {file.role for file in sample.files}
        if roles != {"R1", "R2"}:
            raise PreparationError(f"paired-end sample is missing R1 or R2: {sample.sample_id}")
        sample_paths[sample.sample_id] = {}
        for file in sample.files:
            destination = paths.raw / dataset.experiment_accession / file.filename
            verification = _verified_file(
                url=str(file.url),
                destination=destination,
                expected_bytes=file.expected_bytes,
                expected_md5=file.expected_md5,
                client=client,
                paths=paths,
                now=now,
            )
            sample_paths[sample.sample_id][file.role] = destination.resolve()
            input_rows.append(
                InputManifestRow(
                    sample_id=sample.sample_id,
                    biological_replicate=sample.biological_replicate,
                    role=file.role,
                    file_accession=file.file_accession,
                    filename=file.filename,
                    path=str(destination.resolve()),
                    expected_bytes=file.expected_bytes,
                    observed_bytes=verification.observed_bytes or 0,
                    expected_md5=file.expected_md5,
                    observed_md5=verification.observed_md5 or "",
                    sha256=verification.sha256 or "",
                )
            )

    reference_rows: list[ReferenceManifestRow] = []
    reference_paths: dict[str, Path] = {}
    for file in reference.files:
        destination = paths.reference / reference.reference_profile_id / file.filename
        verification = _verified_file(
            url=str(file.url),
            destination=destination,
            expected_bytes=file.expected_bytes,
            expected_md5=file.expected_md5,
            client=client,
            paths=paths,
            now=now,
        )
        reference_paths[file.role] = destination.resolve()
        reference_rows.append(
            ReferenceManifestRow(
                role=file.role,
                filename=file.filename,
                path=str(destination.resolve()),
                expected_bytes=file.expected_bytes,
                observed_bytes=verification.observed_bytes or 0,
                expected_md5=file.expected_md5,
                observed_md5=verification.observed_md5 or "",
                sha256=verification.sha256 or "",
            )
        )

    input_manifest = run_directory / "input_manifest.tsv"
    reference_manifest = run_directory / "reference_manifest.tsv"
    write_tsv(input_manifest, input_rows)
    write_tsv(reference_manifest, reference_rows)

    samplesheet = run_directory / "samplesheet.csv"
    _write_samplesheet(
        samplesheet,
        [
            {
                "sample": sample.sample_id,
                "fastq_1": str(sample_paths[sample.sample_id]["R1"]),
                "fastq_2": str(sample_paths[sample.sample_id]["R2"]),
                "strandedness": dataset.strandedness,
                "seq_platform": "ILLUMINA",
                "seq_center": "CSHL",
            }
            for sample in selected_samples
        ],
    )

    repo_root = Path(__file__).resolve().parents[2]
    template_path = repo_root / "configs" / "params" / f"{stage_id.lower()}.yaml"
    scientific_parameters = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    effective_parameters = {
        **scientific_parameters,
        "input": str(samplesheet.resolve()),
        "outdir": str((paths.results / stage_id / run_id).resolve()),
        "fasta": str(reference_paths["genome_fasta"]),
        "gtf": str(reference_paths["annotation_gtf"]),
    }
    parameters = run_directory / "parameters.yaml"
    _atomic_write_text(
        parameters,
        yaml.safe_dump(effective_parameters, sort_keys=False, allow_unicode=True),
    )

    result = PreparationResult(
        status="PREPARED",
        stage_id=stage_id,
        run_id=run_id,
        input_manifest_path=input_manifest,
        reference_manifest_path=reference_manifest,
        samplesheet_path=samplesheet,
        parameters_path=parameters,
        input_manifest_sha256=manifest_sha256(input_manifest),
        reference_manifest_sha256=manifest_sha256(reference_manifest),
        samplesheet_sha256=hash_file(samplesheet, "sha256"),
        scientific_template_sha256=hash_file(template_path, "sha256"),
        parameters_sha256=hash_file(parameters, "sha256"),
    )
    atomic_write_json(
        run_directory / "preparation.json", result.model_dump(mode="json")
    )
    if state.status == RunStatus.PREFLIGHT_PASSED:
        store.transition(run_id, RunStatus.PREPARED)
    logger.event("prepare", "stage_prepared", "PASS", stage_id=stage_id)
    return result
