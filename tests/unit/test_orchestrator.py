from pathlib import Path

from rnaseq_mvp.orchestrator import execute_stage


class FakeServices:
    def __init__(self, preflight_result="PASS", validation_result="PASS") -> None:
        self.preflight_result = preflight_result
        self.validation_result = validation_result
        self.calls: list[str] = []

    def preflight(self, profile: str, workspace: Path) -> str:
        self.calls.append("preflight")
        return self.preflight_result

    def prepare(self, stage_id: str, workspace: Path) -> str:
        self.calls.append("prepare")
        return "T2A_20260901T013000Z"

    def run(self, stage_id: str, run_id: str, profile: str, workspace: Path) -> str:
        self.calls.append("run")
        return "EXECUTED"

    def validate(self, stage_id: str, run_id: str, workspace: Path) -> str:
        self.calls.append("validate")
        return self.validation_result


def test_execute_stops_when_preflight_fails(tmp_path: Path) -> None:
    services = FakeServices(preflight_result="FAIL")

    summary = execute_stage("T2A", "server_docker", tmp_path, services)

    assert summary.status == "PREFLIGHT_FAILED"
    assert services.calls == ["preflight"]


def test_execute_stops_at_awaiting_review(tmp_path: Path) -> None:
    services = FakeServices(validation_result="WARN")

    summary = execute_stage("T2A", "server_docker", tmp_path, services)

    assert services.calls == ["preflight", "prepare", "run", "validate"]
    assert summary.status == "AWAITING_REVIEW"
    assert summary.validation_status == "WARN"
