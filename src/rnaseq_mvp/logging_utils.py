from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REDACTED = "***REDACTED***"
SENSITIVE_KEYS = {
    "token",
    "password",
    "private_key",
}


def _redact(value: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return REDACTED

    if isinstance(value, Mapping):
        return {
            str(item_key): _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, list):
        return [_redact(item) for item in value]

    if isinstance(value, tuple):
        return [_redact(item) for item in value]

    return value


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("log timestamp must be timezone-aware")

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


class RunLogger:
    def __init__(
        self,
        log_directory: Path,
        run_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.log_directory = log_directory
        self.run_id = run_id
        self.clock = clock or (
            lambda: datetime.now(timezone.utc)
        )
        self.human_log_path = log_directory / "mvp.log"
        self.event_log_path = log_directory / "events.jsonl"
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def _append(self, path: Path, content: str) -> None:
        with path.open(
            "a",
            encoding="utf-8",
            newline="",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    def event(
        self,
        component: str,
        event: str,
        status: str,
        **fields: Any,
    ) -> None:
        timestamp = _utc_timestamp(self.clock())
        redacted_fields = _redact(fields)
        payload = {
            "timestamp": timestamp,
            "run_id": self.run_id,
            "component": component,
            "event": event,
            "status": status,
            **redacted_fields,
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

        self._append(
            self.event_log_path,
            f"{serialized}\n",
        )
        self._append(
            self.human_log_path,
            (
                f"{timestamp} [{status}] "
                f"{component}.{event} "
                f"run_id={self.run_id} "
                f"{json.dumps(redacted_fields, ensure_ascii=False, sort_keys=True, default=str)}\n"
            ),
        )
