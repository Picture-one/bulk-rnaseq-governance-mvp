from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.preflight import RealSystemProbe, run_preflight, write_preflight_report
from rnaseq_mvp.prepare import prepare_stage
from rnaseq_mvp.runner import RealProcessExecutor, run_stage
from rnaseq_mvp.state import RunStatus, StateStore
from rnaseq_mvp.validator import validate_stage


class ExecutionServices(Protocol):
    def preflight(self, profile: str, workspace: Path) -> str: ...

    def prepare(self, stage_id: str, workspace: Path) -> str: ...

    def run(
        self, stage_id: str, run_id: str, profile: str, workspace: Path
    ) -> str: ...

    def validate(self, stage_id: str, run_id: str, workspace: Path) -> str: ...


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    run_id: str | None
    status: Literal["PREFLIGHT_FAILED", "VALIDATION_FAILED", "AWAITING_REVIEW"]
    validation_status: str | None = None


class StatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    run_id: str | None
    status: str
    last_error: str | None
    next_action: str
    release_allowed: bool


class RealExecutionServices:
    def __init__(self, registry: DefinitionRegistry) -> None:
        self.registry = registry

    def preflight(self, profile: str, workspace: Path) -> str:
        report = run_preflight(profile, workspace, RealSystemProbe.collect(workspace))
        write_preflight_report(report, workspace)
        return report.status

    def prepare(self, stage_id: str, workspace: Path) -> str:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=20.0),
        ) as client:
            result = prepare_stage(
                stage_id,
                workspace,
                self.registry,
                client,
                datetime.now(timezone.utc),
            )
        return result.run_id

    def run(
        self, stage_id: str, run_id: str, profile: str, workspace: Path
    ) -> str:
        result = run_stage(
            stage_id,
            run_id,
            profile,
            workspace,
            self.registry,
            RealProcessExecutor(),
            resume=True,
        )
        return result.status

    def validate(self, stage_id: str, run_id: str, workspace: Path) -> str:
        return validate_stage(stage_id, run_id, workspace, self.registry).status


def execute_stage(
    stage_id: str,
    profile: str,
    workspace: Path,
    services: ExecutionServices,
) -> ExecutionSummary:
    if services.preflight(profile, workspace) != "PASS":
        return ExecutionSummary(
            stage_id=stage_id,
            run_id=None,
            status="PREFLIGHT_FAILED",
        )
    run_id = services.prepare(stage_id, workspace)
    services.run(stage_id, run_id, profile, workspace)
    validation_status = services.validate(stage_id, run_id, workspace)
    if validation_status == "FAIL":
        return ExecutionSummary(
            stage_id=stage_id,
            run_id=run_id,
            status="VALIDATION_FAILED",
            validation_status=validation_status,
        )
    return ExecutionSummary(
        stage_id=stage_id,
        run_id=run_id,
        status="AWAITING_REVIEW",
        validation_status=validation_status,
    )


_NEXT_ACTION = {
    RunStatus.NEW: "run preflight",
    RunStatus.PREFLIGHT_PASSED: "prepare inputs",
    RunStatus.PREPARED: "run pipeline",
    RunStatus.RUNNING: "wait for pipeline",
    RunStatus.EXECUTED: "validate results",
    RunStatus.RUN_FAILED: "inspect logs and resume run",
    RunStatus.VALIDATED_PASS: "advance to review",
    RunStatus.VALIDATED_WITH_WARNINGS: "advance to review",
    RunStatus.VALIDATION_FAILED: "resolve validation failures",
    RunStatus.AWAITING_REVIEW: "record human review",
    RunStatus.REVIEW_ACCEPTED: "create release package",
    RunStatus.REVIEW_REJECTED: "do not release",
    RunStatus.PACKAGED: "use governed release",
}


def stage_status(stage_id: str, workspace: Path) -> StatusSummary:
    runs = workspace.resolve() / "runs"
    candidates = sorted(
        (
            path
            for path in runs.glob(f"{stage_id}_*/state.json")
            if path.is_file()
        ),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    if not candidates:
        return StatusSummary(
            stage_id=stage_id,
            run_id=None,
            status="NOT_STARTED",
            last_error=None,
            next_action="run preflight and prepare",
            release_allowed=False,
        )
    run_id = candidates[0].parent.name
    state = StateStore(workspace.resolve()).load(run_id)
    return StatusSummary(
        stage_id=stage_id,
        run_id=run_id,
        status=state.status.value,
        last_error=state.last_error,
        next_action=_NEXT_ACTION[state.status],
        release_allowed=state.status in {RunStatus.REVIEW_ACCEPTED, RunStatus.PACKAGED},
    )
