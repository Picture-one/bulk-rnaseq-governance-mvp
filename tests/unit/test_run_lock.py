from pathlib import Path

import pytest

from rnaseq_mvp.state import StateStore


def test_run_lock_is_exclusive_and_removed_after_clean_exit(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    run_id = "T2A_20260901T013000Z"
    store.create("T2A", run_id)

    lock_path = tmp_path / "runs" / run_id / "run.lock"

    with store.lock(run_id):
        assert lock_path.exists()

        with pytest.raises(FileExistsError, match="run is locked"), store.lock(run_id):
            pass

    assert not lock_path.exists()
