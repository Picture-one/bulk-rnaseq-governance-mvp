from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rnaseq_mvp.logging_utils import RunLogger
from rnaseq_mvp.state import RunStatus, StateStore


class ReviewError(RuntimeError):
    """Raised when a review decision violates governance requirements."""


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    stage_id: str
    run_id: str
    reviewer: str
    decision: Literal["accept", "reject"]
    comment: str
    validation_status: Literal["PASS", "WARN"]
    reviewed_at: datetime


def record_review(
    stage_id: str,
    run_id: str,
    reviewer: str,
    decision: Literal["accept", "reject"],
    comment: str,
    workspace: Path,
    now: datetime,
) -> ReviewRecord:
    if now.tzinfo is None:
        raise ValueError("review timestamp must be timezone-aware")
    reviewer = reviewer.strip()
    comment = comment.strip()
    if not reviewer:
        raise ReviewError("reviewer must not be blank")
    if not comment:
        raise ReviewError("review comment must not be blank")
    run_directory = workspace.resolve() / "runs" / run_id
    record_path = run_directory / "review_record.json"
    if record_path.exists():
        raise FileExistsError("review already recorded")
    store = StateStore(workspace.resolve())
    state = store.load(run_id)
    if state.stage_id != stage_id or state.status != RunStatus.AWAITING_REVIEW:
        raise ReviewError("review requires the matching AWAITING_REVIEW run")
    validation_path = run_directory / "validation_report.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation_status = validation.get("status")
    if validation_status not in {"PASS", "WARN"}:
        raise ReviewError("only PASS or WARN validation can be reviewed")
    if validation_status == "WARN" and len("".join(comment.split())) < 20:
        raise ReviewError("warning review comment requires at least 20 non-whitespace characters")
    record = ReviewRecord(
        stage_id=stage_id,
        run_id=run_id,
        reviewer=reviewer,
        decision=decision,
        comment=comment,
        validation_status=validation_status,
        reviewed_at=now.astimezone(timezone.utc),
    )
    payload = json.dumps(
        record.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
    )
    try:
        with record_path.open("x", encoding="utf-8") as handle:
            handle.write(f"{payload}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise FileExistsError("review already recorded") from error
    next_status = (
        RunStatus.REVIEW_ACCEPTED if decision == "accept" else RunStatus.REVIEW_REJECTED
    )
    store.transition(run_id, next_status)
    RunLogger(run_directory, run_id).event(
        "review", "human_review_recorded", "PASS", decision=decision, reviewer=reviewer
    )
    return record
