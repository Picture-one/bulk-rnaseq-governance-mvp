from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.checksums import hash_file
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.logging_utils import RunLogger
from rnaseq_mvp.manifests import atomic_write_json
from rnaseq_mvp.paths import WorkspacePaths
from rnaseq_mvp.state import RunStatus, StateStore


class PackageError(RuntimeError):
    """Raised when an immutable research package cannot be created."""


class PackageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    run_id: str
    status: Literal["READY_FOR_RESEARCH", "READY_WITH_REVIEWED_WARNINGS"]
    release_directory: Path
    checksums_path: Path


def _copy_verified(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PackageError(f"required package source is missing: {source}")
    shutil.copy2(source, destination)
    if hash_file(source, "sha256") != hash_file(destination, "sha256"):
        raise PackageError(f"copied file hash mismatch: {source.name}")


def _software_versions(run_directory: Path, results: Path) -> Path:
    candidates = [
        run_directory / "pipeline_provenance" / "software_versions.yml",
        results / "pipeline_info" / "software_versions.yml",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        raise PackageError("required package source is missing: software_versions.yml")
    return existing[0]


def _metadata(
    stage_id: str,
    run_id: str,
    registry: DefinitionRegistry,
    validation_status: str,
    release_status: str,
) -> dict:
    stage = registry.stage(stage_id)
    reference = registry.reference(stage.reference_profile_id)
    method = registry.method(stage.method_profile_id)
    return {
        "schema_version": "1.0",
        "stage_id": stage_id,
        "run_id": run_id,
        "release_status": release_status,
        "validation_status": validation_status,
        "measure": "gene-level raw estimated counts",
        "counts_measure_type": method.counts_measure_type,
        "aggregation": method.aggregation,
        "aligner": method.aligner,
        "quantifier": method.quantifier,
        "gene_identifier": {
            "annotation_provider": reference.annotation_provider,
            "annotation_release": reference.annotation_release,
            "genome_build": f"{reference.genome_build}.{reference.assembly_patch}",
            "versioned_gene_ids": True,
        },
    }


def package_run(
    stage_id: str,
    run_id: str,
    workspace: Path,
    registry: DefinitionRegistry,
) -> PackageResult:
    paths = WorkspacePaths.from_root(workspace)
    store = StateStore(paths.root)
    state = store.load(run_id)
    if state.stage_id != stage_id or state.status != RunStatus.REVIEW_ACCEPTED:
        raise PackageError("package requires the matching REVIEW_ACCEPTED run")
    run_directory = paths.runs / run_id
    validation = json.loads(
        (run_directory / "validation_report.json").read_text(encoding="utf-8")
    )
    validation_status = validation.get("status")
    if validation_status == "PASS":
        release_status = "READY_FOR_RESEARCH"
    elif validation_status == "WARN":
        release_status = "READY_WITH_REVIEWED_WARNINGS"
    else:
        raise PackageError("accepted run must have PASS or WARN validation")
    review = json.loads(
        (run_directory / "review_record.json").read_text(encoding="utf-8")
    )
    if review.get("decision") != "accept":
        raise PackageError("review record is not accepted")
    parameters = yaml.safe_load(
        (run_directory / "parameters.yaml").read_text(encoding="utf-8")
    )
    results = Path(parameters["outdir"])
    star = results / "star_salmon"
    sources = {
        "gene_counts_raw_estimated.tsv": star / "salmon.merged.gene_counts.tsv",
        "gene_tpm.tsv": star / "salmon.merged.gene_tpm.tsv",
        "gene_lengths.tsv": star / "salmon.merged.gene_lengths.tsv",
        "multiqc_report.html": results
        / "multiqc"
        / "star_salmon"
        / "multiqc_report.html",
        "input_manifest.tsv": run_directory / "input_manifest.tsv",
        "reference_manifest.tsv": run_directory / "reference_manifest.tsv",
        "samplesheet.csv": run_directory / "samplesheet.csv",
        "parameters.yaml": run_directory / "parameters.yaml",
        "validation_report.json": run_directory / "validation_report.json",
        "review_record.json": run_directory / "review_record.json",
        "software_versions.yml": _software_versions(run_directory, results),
        "run_provenance.json": run_directory / "run_provenance.json",
    }
    release_parent = paths.release / stage_id
    release_parent.mkdir(parents=True, exist_ok=True)
    target = release_parent / run_id
    if target.exists():
        raise FileExistsError(f"release package already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=release_parent))
    try:
        for filename, source in sources.items():
            _copy_verified(source, temporary / filename)
        metadata = _metadata(
            stage_id, run_id, registry, validation_status, release_status
        )
        atomic_write_json(
            temporary / "gene_counts_raw_estimated.metadata.json", metadata
        )
        readme = (
            "Governed Bulk RNA-seq release package\n"
            f"Stage: {stage_id}\nRun: {run_id}\nStatus: {release_status}\n"
            f"Validation: {validation_status}\n"
            "Counts are unscaled gene-level estimated counts produced by Salmon/tximport.\n"
            "Use the metadata, validation report, review record and provenance together.\n"
        )
        (temporary / "README.txt").write_text(readme, encoding="utf-8")
        checksum_lines = [
            f"{hash_file(path, 'sha256')}  {path.name}"
            for path in temporary.iterdir()
            if path.is_file() and path.name != "checksums.sha256"
        ]
        checksum_lines.sort()
        (temporary / "checksums.sha256").write_text(
            "\n".join(checksum_lines) + "\n", encoding="utf-8"
        )
        for line in checksum_lines:
            expected_hash, filename = line.split("  ", 1)
            if hash_file(temporary / filename, "sha256") != expected_hash:
                raise PackageError(f"release checksum verification failed: {filename}")
        os.replace(temporary, target)
    except (OSError, PackageError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    store.transition(run_id, RunStatus.PACKAGED)
    RunLogger(run_directory, run_id).event(
        "package", "release_package_created", "PASS", release_status=release_status
    )
    return PackageResult(
        stage_id=stage_id,
        run_id=run_id,
        status=release_status,
        release_directory=target,
        checksums_path=target / "checksums.sha256",
    )
