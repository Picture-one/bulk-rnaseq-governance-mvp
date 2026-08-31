from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.manifests import atomic_write_json

ProfileName = Literal["local_docker", "server_docker"]
CheckStatus = Literal["PASS", "WARN", "FAIL"]


@dataclass(frozen=True)
class StaticSystemProbe:
    system: str
    architecture: str
    cpus: int
    memory_gib: float
    disk_free_gib: float
    java_version: str
    nextflow_version: str
    docker_version: str
    docker_hello_ok: bool
    reachable_urls: dict[str, bool]


class SystemProbe(Protocol):
    system: str
    architecture: str
    cpus: int
    memory_gib: float
    disk_free_gib: float
    java_version: str
    nextflow_version: str
    docker_version: str
    docker_hello_ok: bool
    reachable_urls: dict[str, bool]


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: CheckStatus
    observed: str
    required: str
    message: str


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: ProfileName
    workspace: Path
    status: CheckStatus
    created_at: datetime
    checks: list[CheckResult]

    def result(self, name: str) -> CheckResult:
        for check in self.checks:
            if check.name == name:
                return check

        raise KeyError(f"preflight result not found: {name}")


def _check(
    name: str,
    passed: bool,
    observed: str,
    required: str,
    failure_status: Literal["WARN", "FAIL"],
    failure_message: str,
) -> CheckResult:
    if passed:
        return CheckResult(
            name=name,
            status="PASS",
            observed=observed,
            required=required,
            message="requirement satisfied",
        )

    return CheckResult(
        name=name,
        status=failure_status,
        observed=observed,
        required=required,
        message=failure_message,
    )


def _overall_status(
    checks: list[CheckResult],
) -> CheckStatus:
    statuses = {check.status for check in checks}

    if "FAIL" in statuses:
        return "FAIL"

    if "WARN" in statuses:
        return "WARN"

    return "PASS"


def run_preflight(
    profile: ProfileName,
    workspace: Path,
    probe: SystemProbe,
) -> PreflightReport:
    if profile not in {"local_docker", "server_docker"}:
        raise ValueError(f"unsupported profile: {profile}")

    resource_failure_status: Literal["WARN", "FAIL"] = (
        "FAIL" if profile == "server_docker" else "WARN"
    )
    platform_failure_status: Literal["WARN", "FAIL"] = (
        "FAIL" if profile == "server_docker" else "WARN"
    )

    checks = [
        _check(
            name="system",
            passed=probe.system == "Linux",
            observed=probe.system,
            required="Linux",
            failure_status=platform_failure_status,
            failure_message="Linux is required for the frozen execution profile",
        ),
        _check(
            name="architecture",
            passed=probe.architecture in {"x86_64", "amd64"},
            observed=probe.architecture,
            required="x86_64",
            failure_status=platform_failure_status,
            failure_message="x86_64 architecture is required",
        ),
        _check(
            name="cpu",
            passed=probe.cpus >= 16,
            observed=str(probe.cpus),
            required=">= 16 logical CPUs",
            failure_status=resource_failure_status,
            failure_message="available CPU count is below the recommended threshold",
        ),
        _check(
            name="memory",
            passed=probe.memory_gib >= 64.0,
            observed=f"{probe.memory_gib:.2f} GiB",
            required=">= 64 GiB",
            failure_status=resource_failure_status,
            failure_message="available memory is below the required threshold",
        ),
        _check(
            name="disk",
            passed=probe.disk_free_gib >= 500.0,
            observed=f"{probe.disk_free_gib:.2f} GiB",
            required=">= 500 GiB free",
            failure_status=resource_failure_status,
            failure_message="available disk space is below the required threshold",
        ),
        _check(
            name="java",
            passed=bool(
                re.search(
                    r"\b17(?:\.|\b)",
                    probe.java_version,
                )
            ),
            observed=probe.java_version,
            required="Java 17",
            failure_status="FAIL",
            failure_message="Java 17 is required",
        ),
        _check(
            name="nextflow",
            passed="25.10.4" in probe.nextflow_version,
            observed=probe.nextflow_version,
            required="Nextflow 25.10.4",
            failure_status="FAIL",
            failure_message="the frozen Nextflow version is required",
        ),
        _check(
            name="docker_version",
            passed=(
                bool(probe.docker_version.strip())
                and not probe.docker_version.lower().startswith("unavailable:")
            ),
            observed=probe.docker_version,
            required="Docker CLI available",
            failure_status="FAIL",
            failure_message="Docker CLI is unavailable",
        ),
        _check(
            name="docker_daemon",
            passed=probe.docker_hello_ok,
            observed=str(probe.docker_hello_ok),
            required="docker hello-world succeeds",
            failure_status="FAIL",
            failure_message="Docker daemon is unavailable",
        ),
    ]

    for endpoint in sorted(probe.reachable_urls):
        reachable = probe.reachable_urls[endpoint]
        checks.append(
            _check(
                name=f"network_{endpoint}",
                passed=reachable,
                observed=str(reachable),
                required="reachable",
                failure_status="FAIL",
                failure_message=f"required endpoint is unreachable: {endpoint}",
            )
        )

    return PreflightReport(
        profile=profile,
        workspace=workspace.expanduser().resolve(),
        status=_overall_status(checks),
        created_at=datetime.now(timezone.utc),
        checks=checks,
    )


REQUIRED_URLS = {
    "github": "https://github.com/nf-core/rnaseq",
    "encode": "https://www.encodeproject.org/",
    "gencode": (
        "https://ftp.ebi.ac.uk/pub/databases/gencode/"
        "Gencode_human/release_50/"
    ),
    "container_registry": "https://registry-1.docker.io/v2/",
}


def _run_command(
    arguments: list[str],
    timeout_seconds: int,
    environment: dict[str, str] | None = None,
) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return False, str(error)

    output = "\n".join(
        part.strip()
        for part in (
            completed.stdout,
            completed.stderr,
        )
        if part.strip()
    )

    return completed.returncode == 0, output or "no output"


def _read_memory_gib() -> float:
    meminfo = Path("/proc/meminfo")

    if not meminfo.is_file():
        return 0.0

    for line in meminfo.read_text(
        encoding="utf-8"
    ).splitlines():
        if line.startswith("MemTotal:"):
            kibibytes = int(line.split()[1])
            return kibibytes / (1024 * 1024)

    return 0.0


def _url_reachable(url: str) -> bool:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
        ) as client:
            response = client.head(url)

            if response.status_code == 405:
                response = client.get(url)

            return response.status_code < 500
    except httpx.HTTPError:
        return False


@dataclass(frozen=True)
class RealSystemProbe(StaticSystemProbe):
    @classmethod
    def collect(
        cls,
        workspace: Path,
    ) -> RealSystemProbe:
        workspace = workspace.expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        java_ok, java_output = _run_command(
            ["java", "-version"],
            timeout_seconds=30,
        )

        nextflow_environment = {
            **os.environ,
            "NXF_VER": "25.10.4",
        }
        nextflow_ok, nextflow_output = _run_command(
            ["nextflow", "-version"],
            timeout_seconds=30,
            environment=nextflow_environment,
        )

        docker_ok, docker_output = _run_command(
            ["docker", "--version"],
            timeout_seconds=30,
        )
        docker_hello_ok, _ = _run_command(
            [
                "docker",
                "run",
                "--rm",
                "hello-world",
            ],
            timeout_seconds=120,
        )

        disk_free_gib = (
            shutil.disk_usage(workspace).free
            / (1024**3)
        )

        return cls(
            system=platform.system(),
            architecture=platform.machine(),
            cpus=os.cpu_count() or 0,
            memory_gib=_read_memory_gib(),
            disk_free_gib=disk_free_gib,
            java_version=(
                java_output
                if java_ok
                else f"unavailable: {java_output}"
            ),
            nextflow_version=(
                nextflow_output
                if nextflow_ok
                else f"unavailable: {nextflow_output}"
            ),
            docker_version=(
                docker_output
                if docker_ok
                else f"unavailable: {docker_output}"
            ),
            docker_hello_ok=docker_hello_ok,
            reachable_urls={
                name: _url_reachable(url)
                for name, url in REQUIRED_URLS.items()
            },
        )


def write_preflight_report(
    report: PreflightReport,
    workspace: Path,
) -> Path:
    report_path = (
        workspace.expanduser().resolve()
        / "reports"
        / "preflight_report.json"
    )
    atomic_write_json(
        report_path,
        report.model_dump(mode="json"),
    )
    return report_path
