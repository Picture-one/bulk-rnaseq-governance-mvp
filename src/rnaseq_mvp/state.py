from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.manifests import atomic_write_json


class RunStatus(str, Enum):
    NEW = "NEW"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    EXECUTED = "EXECUTED"
    RUN_FAILED = "RUN_FAILED"
    VALIDATED_PASS = "VALIDATED_PASS"
    VALIDATED_WITH_WARNINGS = "VALIDATED_WITH_WARNINGS"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    REVIEW_ACCEPTED = "REVIEW_ACCEPTED"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    PACKAGED = "PACKAGED"


ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.NEW: {
        RunStatus.PREFLIGHT_PASSED,
    },
    RunStatus.PREFLIGHT_PASSED: {
        RunStatus.PREPARED,
    },
    RunStatus.PREPARED: {
        RunStatus.RUNNING,
    },
    RunStatus.RUNNING: {
        RunStatus.EXECUTED,
        RunStatus.RUN_FAILED,
    },
    RunStatus.RUN_FAILED: {
        RunStatus.RUNNING,
    },
    RunStatus.EXECUTED: {
        RunStatus.VALIDATED_PASS,
        RunStatus.VALIDATED_WITH_WARNINGS,
        RunStatus.VALIDATION_FAILED,
    },
    RunStatus.VALIDATED_PASS: {
        RunStatus.AWAITING_REVIEW,
    },
    RunStatus.VALIDATED_WITH_WARNINGS: {
        RunStatus.AWAITING_REVIEW,
    },
    RunStatus.AWAITING_REVIEW: {
        RunStatus.REVIEW_ACCEPTED,
        RunStatus.REVIEW_REJECTED,
        RunStatus.VALIDATION_FAILED,
    },
    RunStatus.REVIEW_ACCEPTED: {
        RunStatus.PACKAGED,
    },
}


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    stage_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None


def new_run_id(stage_id: str, now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("run ID timestamp must be timezone-aware")

    utc_now = now.astimezone(timezone.utc)
    timestamp = utc_now.strftime("%Y%m%dT%H%M%SZ")
    return f"{stage_id}_{timestamp}"


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.runs_directory = root / "runs"

    def _run_directory(self, run_id: str) -> Path:
        return self.runs_directory / run_id

    def _state_path(self, run_id: str) -> Path:
        return self._run_directory(run_id) / "state.json"

    def create(
        self,
        stage_id: str,
        run_id: str,
    ) -> RunState:
        state_path = self._state_path(run_id)

        if state_path.exists():
            raise FileExistsError(f"run state already exists: {run_id}")

        state_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        state = RunState(
            run_id=run_id,
            stage_id=stage_id,
            status=RunStatus.NEW,
            created_at=now,
            updated_at=now,
        )
        atomic_write_json(
            state_path,
            state.model_dump(mode="json"),
        )
        return state

    def load(self, run_id: str) -> RunState:
        state_path = self._state_path(run_id)
        payload = json.loads(
            state_path.read_text(encoding="utf-8")
        )
        return RunState.model_validate(payload)

    def transition(
        self,
        run_id: str,
        next_status: RunStatus,
    ) -> RunState:
        state = self.load(run_id)
        allowed = ALLOWED_TRANSITIONS.get(state.status, set())

        if next_status not in allowed:
            raise ValueError(
                "illegal transition: "
                f"{state.status.value} -> {next_status.value}"
            )

        updated = state.model_copy(
            update={
                "status": next_status,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        atomic_write_json(
            self._state_path(run_id),
            updated.model_dump(mode="json"),
        )
        return updated
    @contextmanager
    def lock(self, run_id: str) -> Iterator[Path]:
        lock_path = self._run_directory(run_id) / "run.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            raise FileExistsError(
                f"run is locked: {run_id}"
            ) from error

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                payload = {
                    "pid": os.getpid(),
                    "created_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            yield lock_path
        finally:
            lock_path.unlink(missing_ok=True)
