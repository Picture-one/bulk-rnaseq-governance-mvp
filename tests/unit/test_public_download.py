from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rnaseq_mvp.public_download import (
    PublicDownloadError,
    download_public_fastqs,
)


def test_public_download_reuses_existing_valid_fastq(tmp_path: Path) -> None:
    content = b"valid-fastq\n"
    fastq = tmp_path / "SRR1.fastq.gz"
    fastq.write_bytes(content)
    manifest = _write_manifest(tmp_path, "SRR1.fastq.gz", content)

    def fail_downloader(url: str, destination: Path, timeout_seconds: float) -> None:
        raise AssertionError("downloader should not be called")

    result = download_public_fastqs(
        manifest_tsv=manifest,
        downloader=fail_downloader,
    )

    assert result.file_count == 1
    assert result.reused_count == 1
    assert result.downloaded_count == 0
    assert result.repaired_count == 0
    assert result.results[0].status == "reused"


def test_public_download_deletes_invalid_file_and_redownloads(tmp_path: Path) -> None:
    expected = b"correct-fastq\n"
    fastq = tmp_path / "SRR1.fastq.gz"
    fastq.write_bytes(b"corrupt")
    manifest = _write_manifest(tmp_path, "SRR1.fastq.gz", expected)

    calls: list[str] = []

    def fake_downloader(url: str, destination: Path, timeout_seconds: float) -> None:
        calls.append(url)
        destination.write_bytes(expected)

    result = download_public_fastqs(
        manifest_tsv=manifest,
        downloader=fake_downloader,
    )

    assert calls == ["https://example.org/SRR1.fastq.gz"]
    assert fastq.read_bytes() == expected
    assert result.downloaded_count == 1
    assert result.reused_count == 0
    assert result.repaired_count == 1
    assert result.results[0].status == "downloaded"
    assert result.results[0].attempts == 1


def test_public_download_fails_after_max_attempts(tmp_path: Path) -> None:
    expected = b"correct-fastq\n"
    manifest = _write_manifest(tmp_path, "SRR1.fastq.gz", expected)

    def bad_downloader(url: str, destination: Path, timeout_seconds: float) -> None:
        destination.write_bytes(b"wrong")

    with pytest.raises(PublicDownloadError, match="Failed to download verified FASTQ"):
        download_public_fastqs(
            manifest_tsv=manifest,
            max_attempts=2,
            downloader=bad_downloader,
        )

    assert not (tmp_path / "SRR1.fastq.gz").exists()


def _write_manifest(tmp_path: Path, file_name: str, expected_content: bytes) -> Path:
    manifest = tmp_path / "manifest.tsv"
    expected_md5 = hashlib.md5(expected_content, usedforsecurity=False).hexdigest()
    expected_bytes = len(expected_content)
    local_path = tmp_path / file_name
    manifest.write_text(
        "\t".join(
            [
                "study_accession",
                "sample_accession",
                "experiment_accession",
                "run_accession",
                "file_role",
                "file_name",
                "download_url",
                "expected_bytes",
                "expected_md5",
                "local_path",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "GSE_TEST",
                "SAMN_TEST",
                "SRX_TEST",
                "SRR1",
                "SE",
                file_name,
                f"https://example.org/{file_name}",
                str(expected_bytes),
                expected_md5,
                str(local_path),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest
