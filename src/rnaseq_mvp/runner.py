from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.checksums import hash_file
from rnaseq_mvp.constants import MVP_VERSION
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.logging_utils import RunLogger
from rnaseq_mvp.manifests import atomic_write_json
from rnaseq_mvp.paths import WorkspacePaths
from rnaseq_mvp.prepare import PreparationResult
from rnaseq_mvp.state import RunStatus, StateStore


class IntegrityError(RuntimeError):
    """Raised when a prepared input or parameter artifact has changed."""


class PipelineRunError(RuntimeError):
    """Raised when the pinned workflow cannot complete successfully."""


class ProcessExecutor(Protocol):
    def run(
        self,
        args: list[str],
        cwd: Path,
        env: dict[str, str],
        stdout_path: Path,
        stderr_path: Path,
    ) -> subprocess.CompletedProcess[str]: ...


class RealProcessExecutor:
    def run(
        self,
        args: list[str],
        cwd: Path,
        env: dict[str, str],
        stdout_path: Path,
        stderr_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        cwd.mkdir(parents=True, exist_ok=True)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_handle,
            stderr_path.open("w", encoding="utf-8") as stderr_handle,
        ):
            return subprocess.run(
                args,
                cwd=cwd,
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                check=False,
            )


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    run_id: str
    status: str
    exit_code: int
    command: list[str]
    provenance_path: Path
    stdout_path: Path
    stderr_path: Path


def build_nextflow_command(
    stage_id: str,
    run_id: str,
    profile: str,
    repo_root: Path,
    workspace: Path,
    resume: bool,
) -> list[str]:
    if profile not in {
        "local_docker",
        "server_docker",
        "server_docker_arm64",
    }:
        raise ValueError(f"unsupported execution profile: {profile}")
    command = [
        "nextflow",
        "run",
        "nf-core/rnaseq",
        "-r",
        "3.26.0",
        "-profile",
        "docker",
        "-params-file",
        str(workspace / "runs" / run_id / "parameters.yaml"),
        "-c",
        str(repo_root / "configs" / "profiles" / f"{profile}.config"),
        "-work-dir",
        str(workspace / "work"),
    ]
    if resume:
        command.append("-resume")
    return command


def _require_preflight(
    workspace: Path,
    profile: str,
    now: datetime,
) -> dict:
    report_path = workspace / "reports" / "preflight_report.json"
    if not report_path.is_file():
        raise PipelineRunError("a PASS preflight report is required")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise PipelineRunError("preflight report is not PASS")
    if report.get("profile") != profile:
        raise PipelineRunError("preflight profile does not match requested profile")
    if Path(report.get("workspace", "")).resolve() != workspace.resolve():
        raise PipelineRunError("preflight report belongs to a different workspace")
    created_at = datetime.fromisoformat(str(report["created_at"]).replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        raise PipelineRunError("preflight timestamp must be timezone-aware")
    if now.astimezone(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(
        hours=24
    ):
        raise PipelineRunError("preflight report is older than 24 hours")
    return report


def _verify_preparation(run_directory: Path) -> PreparationResult:
    preparation_path = run_directory / "preparation.json"
    if not preparation_path.is_file():
        raise IntegrityError("preparation record is missing")
    preparation = PreparationResult.model_validate_json(
        preparation_path.read_text(encoding="utf-8")
    )
    checks = [
        (
            Path(preparation.input_manifest_path),
            preparation.input_manifest_sha256,
            "input manifest changed after prepare",
        ),
        (
            Path(preparation.reference_manifest_path),
            preparation.reference_manifest_sha256,
            "reference manifest changed after prepare",
        ),
        (
            Path(preparation.samplesheet_path),
            preparation.samplesheet_sha256,
            "samplesheet changed after prepare",
        ),
        (
            Path(preparation.parameters_path),
            preparation.parameters_sha256,
            "parameters changed after prepare",
        ),
    ]
    for path, expected_hash, message in checks:
        if not path.is_file() or hash_file(path, "sha256") != expected_hash:
            raise IntegrityError(message)
    return preparation


def _git_commit(repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _copy_optional_provenance(
    workspace: Path,
    output_directory: Path,
    run_directory: Path,
) -> list[str]:
    destination = run_directory / "pipeline_provenance"
    candidates = [
        workspace / ".nextflow.log",
        output_directory / "pipeline_info" / "execution_trace_*.txt",
        output_directory / "pipeline_info" / "execution_report_*.html",
        output_directory / "pipeline_info" / "execution_timeline_*.html",
        output_directory / "pipeline_info" / "software_versions.yml",
    ]
    copied: list[str] = []
    for candidate in candidates:
        matches = list(candidate.parent.glob(candidate.name))
        for source in sorted(matches):
            if not source.is_file():
                continue
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / source.name
            shutil.copy2(source, target)
            copied.append(str(target))
    return copied


def run_stage(
    stage_id: str,
    run_id: str,
    profile: str,
    workspace: Path,
    registry: DefinitionRegistry,
    executor: ProcessExecutor,
    resume: bool,
    now: datetime | None = None,
) -> RunResult:
    started_at = now or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        raise ValueError("run timestamp must be timezone-aware")
    paths = WorkspacePaths.from_root(workspace)
    _require_preflight(paths.root, profile, started_at)
    stage = registry.stage(stage_id)
    method = registry.method(stage.method_profile_id)
    store = StateStore(paths.root)
    state = store.load(run_id)
    if state.stage_id != stage_id:
        raise ValueError("run state belongs to a different stage")
    if state.status not in {RunStatus.PREPARED, RunStatus.RUN_FAILED}:
        raise PipelineRunError(f"run cannot start from state {state.status.value}")

    run_directory = paths.runs / run_id
    preparation = _verify_preparation(run_directory)
    repo_root = Path(__file__).resolve().parents[2]
    command = build_nextflow_command(
        stage_id, run_id, profile, repo_root, paths.root, resume
    )
    parameters = yaml.safe_load(
        Path(preparation.parameters_path).read_text(encoding="utf-8")
    )
    output_directory = Path(parameters["outdir"])
    stdout_path = run_directory / "nextflow.stdout.log"
    stderr_path = run_directory / "nextflow.stderr.log"
    provenance_path = run_directory / "run_provenance.json"
    logger = RunLogger(run_directory, run_id)
    environment = os.environ.copy()
    environment["NXF_VER"] = method.nextflow_version
    completed: subprocess.CompletedProcess[str] | None = None
    error_message: str | None = None

    with store.lock(run_id):
        store.transition(run_id, RunStatus.RUNNING)
        logger.event("run", "pipeline_started", "START", argv=command)
        try:
            completed = executor.run(
                command,
                paths.root,
                environment,
                stdout_path,
                stderr_path,
            )
        except (OSError, subprocess.SubprocessError) as error:
            error_message = str(error)
            store.transition(run_id, RunStatus.RUN_FAILED)
        else:
            if completed.returncode == 0:
                store.transition(run_id, RunStatus.EXECUTED)
            else:
                error_message = f"Nextflow exited with code {completed.returncode}"
                store.transition(run_id, RunStatus.RUN_FAILED)

        ended_at = datetime.now(timezone.utc)
        copied = _copy_optional_provenance(
            paths.root, output_directory, run_directory
        )
        exit_code = completed.returncode if completed is not None else -1
        provenance = {
            "schema_version": "1.0",
            "mvp_version": MVP_VERSION,
            "git_commit": _git_commit(repo_root),
            "stage_id": stage_id,
            "run_id": run_id,
            "pipeline": method.pipeline_name,
            "pipeline_version": method.pipeline_version,
            "nextflow_version": method.nextflow_version,
            "profile": profile,
            "method_profile_id": method.method_profile_id,
            "reference_profile_id": stage.reference_profile_id,
            "input_manifest_sha256": preparation.input_manifest_sha256,
            "reference_manifest_sha256": preparation.reference_manifest_sha256,
            "parameters_sha256": preparation.parameters_sha256,
            "argv": command,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "exit_code": exit_code,
            "error": error_message,
            "copied_pipeline_artifacts": copied,
        }
        atomic_write_json(provenance_path, provenance)

    if error_message is not None:
        logger.event("run", "pipeline_failed", "FAIL", error=error_message)
        raise PipelineRunError(error_message)
    logger.event("run", "pipeline_completed", "PASS")
    return RunResult(
        stage_id=stage_id,
        run_id=run_id,
        status="EXECUTED",
        exit_code=0,
        command=command,
        provenance_path=provenance_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
