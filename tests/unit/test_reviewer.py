import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rnaseq_mvp.reviewer import ReviewError, record_review
from rnaseq_mvp.state import RunStatus, StateStore


def _awaiting_review(tmp_path: Path, validation_status: str = "PASS") -> str:
    run_id = "T2A_20260901T013000Z"
    store = StateStore(tmp_path)
    store.create("T2A", run_id)
    store.transition(run_id, RunStatus.PREFLIGHT_PASSED)
    store.transition(run_id, RunStatus.PREPARED)
    store.transition(run_id, RunStatus.RUNNING)
    store.transition(run_id, RunStatus.EXECUTED)
    if validation_status == "PASS":
        store.transition(run_id, RunStatus.VALIDATED_PASS)
    else:
        store.transition(run_id, RunStatus.VALIDATED_WITH_WARNINGS)
    store.transition(run_id, RunStatus.AWAITING_REVIEW)
    (tmp_path / "runs" / run_id / "validation_report.json").write_text(
        json.dumps({"status": validation_status}), encoding="utf-8"
    )
    return run_id


def test_review_record_is_immutable(tmp_path: Path) -> None:
    run_id = _awaiting_review(tmp_path)
    now = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)
    first = record_review(
        "T2A",
        run_id,
        "reviewer-001",
        "accept",
        "counts, MultiQC and provenance checked",
        tmp_path,
        now,
    )

    assert first.decision == "accept"
    with pytest.raises(FileExistsError, match="review already recorded"):
        record_review(
            "T2A",
            run_id,
            "reviewer-002",
            "reject",
            "second decision must not overwrite",
            tmp_path,
            now,
        )


def test_warning_review_requires_substantive_comment(tmp_path: Path) -> None:
    run_id = _awaiting_review(tmp_path, "WARN")
    now = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)

    with pytest.raises(ReviewError, match="20 non-whitespace"):
        record_review("T2A", run_id, "reviewer", "accept", "too short", tmp_path, now)


@pytest.mark.parametrize("reviewer,comment", [("", "valid comment"), ("reviewer", "")])
def test_review_requires_identity_and_comment(
    tmp_path: Path,
    reviewer: str,
    comment: str,
) -> None:
    run_id = _awaiting_review(tmp_path)
    now = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)

    with pytest.raises(ReviewError):
        record_review("T2A", run_id, reviewer, "accept", comment, tmp_path, now)
