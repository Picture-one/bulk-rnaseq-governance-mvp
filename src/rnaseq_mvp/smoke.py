from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.manifests import atomic_write_json
from rnaseq_mvp.runner import ProcessExecutor


class SmokeTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL"]
    smoke_id: str
    profile: str
    command: list[str]
    outdir: Path
    report_path: Path
    exit_code: int
    missing_outputs: list[str]


def run_smoke_test(
    profile: str,
    workspace: Path,
    executor: ProcessExecutor,
    *,
    now: datetime | None = None,
) -> SmokeTestResult:
    if profile not in {"local_docker", "server_docker"}:
        raise ValueError(f"unsupported execution profile: {profile}")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("smoke timestamp must be timezone-aware")
    smoke_id = f"smoke_{timestamp.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    root = workspace.resolve()
    smoke_directory = root / "smoke" / smoke_id
    outdir = smoke_directory / "results"
    work_directory = root / "smoke_work"
    command = [
        "nextflow",
        "run",
        "nf-core/rnaseq",
        "-r",
        "3.26.0",
        "-profile",
        "test,docker",
        "--outdir",
        str(outdir),
        "-work-dir",
        str(work_directory),
        "-resume",
    ]
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
        report_path=report_path,
        exit_code=completed.returncode,
        missing_outputs=missing,
    )
    atomic_write_json(report_path, result.model_dump(mode="json"))
    return result
