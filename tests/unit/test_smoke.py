import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rnaseq_mvp.smoke import run_smoke_test


class SmokeExecutor:
    def __init__(self) -> None:
        self.args: list[str] | None = None
        self.env: dict[str, str] | None = None

    def run(self, args, cwd, env, stdout_path, stderr_path):
        self.args = args
        self.env = env
        outdir = Path(args[args.index("--outdir") + 1])
        counts = outdir / "star_salmon" / "salmon.merged.gene_counts.tsv"
        multiqc = outdir / "multiqc" / "star_salmon" / "multiqc_report.html"
        counts.parent.mkdir(parents=True)
        multiqc.parent.mkdir(parents=True)
        counts.write_text("gene_id\tgene_name\tS1\nG1\tG1\t1\n", encoding="utf-8")
        multiqc.write_text("<html></html>", encoding="utf-8")
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("ok\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0)


def test_smoke_uses_pinned_versions_and_verifies_outputs(tmp_path: Path) -> None:
    executor = SmokeExecutor()
    now = datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)

    result = run_smoke_test("local_docker", tmp_path, executor, now=now)

    assert result.status == "PASS"
    assert executor.env is not None
    assert executor.env["NXF_VER"] == "25.10.4"
    assert executor.args is not None
    assert executor.args[:8] == [
        "nextflow",
        "run",
        "nf-core/rnaseq",
        "-r",
        "3.26.0",
        "-profile",
        "test,docker",
        "--outdir",
    ]


class EmptySuccessExecutor:
    def run(self, args, cwd, env, stdout_path, stderr_path):
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0)


def test_smoke_fails_if_exit_zero_has_no_outputs(tmp_path: Path) -> None:
    result = run_smoke_test(
        "local_docker",
        tmp_path,
        EmptySuccessExecutor(),
        now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
    )

    assert result.status == "FAIL"
    assert "merged_counts" in result.missing_outputs
    assert "multiqc_report" in result.missing_outputs
