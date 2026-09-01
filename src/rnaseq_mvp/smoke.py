from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.manifests import atomic_write_json
from rnaseq_mvp.runner import ProcessExecutor

PINNED_PIPELINE_REVISION = "3.26.0"

class SmokeAssets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Path
    fasta: Path
    gtf: Path
    transcript_fasta: Path
    additional_fasta: Path
    salmon_index: Path

class SmokeTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL"]
    smoke_id: str
    profile: str
    command: list[str]
    outdir: Path
    work_directory: Path
    report_path: Path
    exit_code: int
    missing_outputs: list[str]

def _load_smoke_assets(manifest: Path) -> SmokeAssets:
    resolved_manifest = manifest.expanduser().resolve()
    payload = yaml.safe_load(
        resolved_manifest.read_text(encoding="utf-8")
    )
    assets = SmokeAssets.model_validate(payload or {})

    resolved_paths: dict[str, Path] = {}
    for name, path in assets:
        expanded_path = path.expanduser()
        if not expanded_path.is_absolute():
            expanded_path = resolved_manifest.parent / expanded_path
        resolved_paths[name] = expanded_path.resolve()

    resolved_assets = SmokeAssets(**resolved_paths)

    for name, path in resolved_assets:
        if not path.is_file():
            raise ValueError(
                f"smoke asset {name} does not exist: {path}"
            )

    return resolved_assets
def _default_smoke_work_directory(workspace: Path) -> Path:
    """Choose a FIFO-capable work directory for Nextflow.

    STAR creates named pipes while aligning reads. WSL's Windows drive mounts
    (for example ``/mnt/e``) cannot create those FIFO files, so only Nextflow's
    disposable work data is moved to the WSL Linux filesystem. Results and
    reports remain in the requested workspace.
    """
    resolved = workspace.expanduser().resolve()
    parts = resolved.as_posix().split("/")
    is_wsl_windows_mount = (
        len(parts) > 3
        and parts[1] == "mnt"
        and len(parts[2]) == 1
        and parts[2].isalpha()
    )
    if not is_wsl_windows_mount:
        return resolved / "smoke_work"

    workspace_key = hashlib.sha256(str(resolved).encode()).hexdigest()[:12]
    return (
        Path.home()
        / ".cache"
        / "rnaseq-mvp"
        / "smoke_work"
        / workspace_key
    )


def _cached_pipeline_matches_revision(path: Path, revision: str) -> bool:
    if not (path / ".git").is_dir():
        return False
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tag_commit = subprocess.run(
            ["git", "-C", str(path), "rev-parse", f"{revision}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(head) and head == tag_commit


def run_smoke_test(
    profile: str,
    workspace: Path,
    executor: ProcessExecutor,
    *,
    now: datetime | None = None,
    resume: bool = True,
    assets_manifest: Path | None = None,
) -> SmokeTestResult:
    if profile not in {
        "local_docker",
        "server_docker",
        "server_docker_arm64",
    }:
        raise ValueError(f"unsupported execution profile: {profile}")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("smoke timestamp must be timezone-aware")
    smoke_id = f"smoke_{timestamp.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    root = workspace.resolve()
    smoke_directory = root / "smoke" / smoke_id
    outdir = smoke_directory / "results"
    configured_work_directory = os.environ.get("RNASEQ_MVP_SMOKE_WORK_DIR")
    work_directory = (
        Path(configured_work_directory).expanduser().resolve()
        if configured_work_directory
        else _default_smoke_work_directory(root)
    )
    repo_root = Path(__file__).resolve().parents[2]
    cached_pipeline = Path.home() / ".nextflow" / "assets" / "nf-core" / "rnaseq"
    use_cached_pipeline = _cached_pipeline_matches_revision(
        cached_pipeline,
        PINNED_PIPELINE_REVISION,
    )
    pipeline_source = str(cached_pipeline) if use_cached_pipeline else "nf-core/rnaseq"
    command = [
        "nextflow",
        "run",
        pipeline_source,
    ]
    if not use_cached_pipeline:
        command.extend(["-r", PINNED_PIPELINE_REVISION])
    command.extend(
        [
            "-profile",
            "test,docker",
            "--outdir",
            str(outdir),
            "--skip_bbsplit",
            "true",
            "--validate_params",
            "false",
            "-work-dir",
            str(work_directory),
        ]
    )
    if assets_manifest is not None:
        assets = _load_smoke_assets(assets_manifest)
        for option, path in [
            ("--input", assets.input),
            ("--fasta", assets.fasta),
            ("--gtf", assets.gtf),
            ("--transcript_fasta", assets.transcript_fasta),
            ("--additional_fasta", assets.additional_fasta),
            ("--salmon_index", assets.salmon_index),
        ]:
            command.extend([option, str(path)])
    if profile == "local_docker":
        config_name = "smoke_local.config"
    elif profile == "server_docker_arm64":
        config_name = "server_docker_arm64.config"
    else:
        config_name = None

    if config_name is not None:
        config_path = (
            repo_root
            / "configs"
            / "profiles"
            / config_name
        )
        command.extend(["-c", str(config_path)])
    if resume:
        command.append("-resume")
    environment = os.environ.copy()
    environment["NXF_VER"] = "25.10.4"
    completed = executor.run(
        command,
        root,
        environment,
        smoke_directory / "nextflow.stdout.log",
        smoke_directory / "nextflow.stderr.log",
    )
    required = {
        "merged_counts": outdir
        / "star_salmon"
        / "salmon.merged.gene_counts.tsv",
        "multiqc_report": outdir
        / "multiqc"
        / "star_salmon"
        / "multiqc_report.html",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    status: Literal["PASS", "FAIL"] = (
        "PASS" if completed.returncode == 0 and not missing else "FAIL"
    )
    report_path = root / "reports" / f"{smoke_id}.json"
    result = SmokeTestResult(
        status=status,
        smoke_id=smoke_id,
        profile=profile,
        command=command,
        outdir=outdir,
        work_directory=work_directory,
        report_path=report_path,
        exit_code=completed.returncode,
        missing_outputs=missing,
    )
    atomic_write_json(report_path, result.model_dump(mode="json"))
    return result
