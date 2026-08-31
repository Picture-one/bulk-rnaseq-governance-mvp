import json
from datetime import datetime, timezone
from pathlib import Path

from rnaseq_mvp.logging_utils import RunLogger


def test_run_logger_writes_dual_logs_and_redacts_secrets(
    tmp_path: Path,
) -> None:
    fixed_now = datetime(
        2026,
        9,
        1,
        1,
        30,
        tzinfo=timezone.utc,
    )
    logger = RunLogger(
        log_directory=tmp_path,
        run_id="T2A_20260901T013000Z",
        clock=lambda: fixed_now,
    )

    logger.event(
        component="prepare",
        event="download_complete",
        status="PASS",
        sample_id="K562_POLYA_REP1",
        token="token-secret",
        password="password-secret",
        private_key="private-key-secret",
    )

    payload = json.loads(
        (tmp_path / "events.jsonl").read_text(
            encoding="utf-8"
        )
    )
    human_log = (tmp_path / "mvp.log").read_text(
        encoding="utf-8"
    )

    assert payload["run_id"] == "T2A_20260901T013000Z"
    assert payload["component"] == "prepare"
    assert payload["event"] == "download_complete"
    assert payload["status"] == "PASS"
    assert payload["sample_id"] == "K562_POLYA_REP1"
    assert payload["token"] == "***REDACTED***"
    assert payload["password"] == "***REDACTED***"
    assert payload["private_key"] == "***REDACTED***"
    assert payload["timestamp"].endswith("Z")

    assert "token-secret" not in human_log
    assert "password-secret" not in human_log
    assert "private-key-secret" not in human_log
