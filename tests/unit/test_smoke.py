import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rnaseq_mvp.smoke import _default_smoke_work_directory, run_smoke_test


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


def test_smoke_uses_pinned_versions_and_verifies_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: tmp_path / "uncached-home"),
    )
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
    config_path = Path(executor.args[executor.args.index("-c") + 1])
    assert config_path.name == "smoke_local.config"
    config = config_path.read_text(encoding="utf-8")
    assert "withLabel: process_medium" in config
    assert "withLabel: process_high" in config
    assert "withName: '.*:SALMON_QUANT'" in config
    assert executor.args[executor.args.index("--skip_bbsplit") + 1] == "true"
    assert executor.args[executor.args.index("--validate_params") + 1] == "false"


def test_arm64_smoke_uses_wave_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: tmp_path / "uncached-home"),
    )
    executor = SmokeExecutor()

    result = run_smoke_test(
        "server_docker_arm64",
        tmp_path,
        executor,
        now=datetime(
            2026,
            9,
            2,
            4,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert result.status == "PASS"
    assert executor.args is not None
    assert (
        executor.args[
            executor.args.index("-profile") + 1
        ]
        == "test,docker"
    )
    config_path = Path(
        executor.args[
            executor.args.index("-c") + 1
        ]
    )
    assert config_path.name == "server_docker_arm64.config"


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


def test_smoke_uses_local_pipeline_checkout_when_cached(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_home = tmp_path / "home"
    cache = fake_home / ".nextflow" / "assets" / "nf-core" / "rnaseq" / ".git"
    cache.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        "rnaseq_mvp.smoke._cached_pipeline_matches_revision",
        lambda path, revision: True,
    )
    executor = SmokeExecutor()

    run_smoke_test(
        "local_docker",
        tmp_path / "workspace",
        executor,
        now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
    )

    assert executor.args is not None
    assert executor.args[2] == str(cache.parent)
    assert "-r" not in executor.args
    assert executor.env is not None
    assert "NXF_OFFLINE" not in executor.env


def test_wsl_windows_mount_uses_linux_filesystem_for_nextflow_work(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    work_directory = _default_smoke_work_directory(
        Path("/mnt/e/research/bulk-rnaseq-governance-mvp")
    )

    assert work_directory.is_relative_to(
        fake_home / ".cache" / "rnaseq-mvp" / "smoke_work"
    )


def test_smoke_work_directory_can_be_overridden(
    tmp_path: Path,
    monkeypatch,
) -> None:
    custom_work = tmp_path / "linux-work"
    monkeypatch.setenv("RNASEQ_MVP_SMOKE_WORK_DIR", str(custom_work))
    executor = SmokeExecutor()

    result = run_smoke_test(
        "local_docker",
        tmp_path / "workspace",
        executor,
        now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
    )

    assert result.work_directory == custom_work.resolve()
    assert executor.args is not None
    assert executor.args[executor.args.index("-work-dir") + 1] == str(
        custom_work.resolve()
    )


def test_fresh_smoke_omits_resume(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: tmp_path / "uncached-home"),
    )
    executor = SmokeExecutor()

    run_smoke_test(
        "local_docker",
        tmp_path / "workspace",
        executor,
        now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
        resume=False,
    )

    assert executor.args is not None
    assert "-resume" not in executor.args
def test_smoke_manifest_overrides_remote_test_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: tmp_path / "uncached-home"),
    )

    assets_directory = tmp_path / "assets"
    assets_directory.mkdir()

    assets = {
        "input": assets_directory / "samplesheet.csv",
        "fasta": assets_directory / "genome.fasta",
        "gtf": assets_directory / "genes.gtf.gz",
        "transcript_fasta": assets_directory / "transcriptome.fasta",
        "additional_fasta": assets_directory / "additional.fa.gz",
        "salmon_index": assets_directory / "salmon.tar.gz",
    }
    for path in assets.values():
        path.write_text("test\n", encoding="utf-8")

    manifest = assets_directory / "smoke-assets.yaml"
    manifest.write_text(
        "\n".join(
            f"{name}: {path}"
            for name, path in assets.items()
        )
        + "\n",
        encoding="utf-8",
    )

    executor = SmokeExecutor()
    run_smoke_test(
        "local_docker",
        tmp_path / "workspace",
        executor,
        now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
        assets_manifest=manifest,
    )

    assert executor.args is not None
    for option, path in assets.items():
        cli_option = "--input" if option == "input" else f"--{option}"
        assert executor.args[executor.args.index(cli_option) + 1] == str(
            path.resolve()
        )
def test_smoke_manifest_rejects_missing_asset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: tmp_path / "uncached-home"),
    )

    assets_directory = tmp_path / "assets"
    assets_directory.mkdir()

    assets = {
        "input": assets_directory / "samplesheet.csv",
        "fasta": assets_directory / "genome.fasta",
        "gtf": assets_directory / "missing-genes.gtf.gz",
        "transcript_fasta": assets_directory / "transcriptome.fasta",
        "additional_fasta": assets_directory / "additional.fa.gz",
        "salmon_index": assets_directory / "salmon.tar.gz",
    }

    for name, path in assets.items():
        if name != "gtf":
            path.write_text("test\n", encoding="utf-8")

    manifest = assets_directory / "smoke-assets.yaml"
    manifest.write_text(
        "\n".join(
            f"{name}: {path}"
            for name, path in assets.items()
        )
        + "\n",
        encoding="utf-8",
    )

    executor = SmokeExecutor()

    with pytest.raises(ValueError, match="gtf.*does not exist"):
        run_smoke_test(
            "local_docker",
            tmp_path / "workspace",
            executor,
            now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
            assets_manifest=manifest,
        )

    assert executor.args is None
def test_smoke_manifest_resolves_paths_relative_to_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: tmp_path / "uncached-home"),
    )

    assets_directory = tmp_path / "portable-assets"
    assets_directory.mkdir()

    relative_assets = {
        "input": "samplesheet.csv",
        "fasta": "genome.fasta",
        "gtf": "genes.gtf.gz",
        "transcript_fasta": "transcriptome.fasta",
        "additional_fasta": "additional.fa.gz",
        "salmon_index": "salmon.tar.gz",
    }

    for filename in relative_assets.values():
        (assets_directory / filename).write_text(
            "test\n",
            encoding="utf-8",
        )

    manifest = assets_directory / "smoke-assets.yaml"
    manifest.write_text(
        "\n".join(
            f"{name}: {filename}"
            for name, filename in relative_assets.items()
        )
        + "\n",
        encoding="utf-8",
    )

    executor = SmokeExecutor()
    run_smoke_test(
        "local_docker",
        tmp_path / "workspace",
        executor,
        now=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
        assets_manifest=manifest,
    )

    assert executor.args is not None
    for option, filename in relative_assets.items():
        cli_option = "--input" if option == "input" else f"--{option}"
        assert executor.args[executor.args.index(cli_option) + 1] == str(
            (assets_directory / filename).resolve()
        )
