from datetime import datetime, timezone
from pathlib import Path

import pytest

from rnaseq_mvp.state import RunStatus, StateStore, new_run_id


def test_state_store_rejects_backward_transition(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    state = store.create(
        "T2A",
        "T2A_20260901T013000Z",
    )
    state = store.transition(
        state.run_id,
        RunStatus.PREFLIGHT_PASSED,
    )

    with pytest.raises(ValueError, match="illegal transition"):
        store.transition(state.run_id, RunStatus.NEW)


def test_run_id_is_utc_and_deterministic() -> None:
    now = datetime(
        2026,
        9,
        1,
        1,
        30,
        tzinfo=timezone.utc,
    )

    assert new_run_id("T2A", now) == "T2A_20260901T013000Z"
