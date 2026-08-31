import gzip
import hashlib
from pathlib import Path

from rnaseq_mvp.checksums import (
    verify_expected_file,
    verify_gzip,
)


def test_verify_expected_gzip_file_returns_complete_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reads.fastq.gz"

    with gzip.open(path, "wb") as handle:
        handle.write(b"@read1\nACGT\n+\nIIII\n")

    content = path.read_bytes()
    expected_md5 = hashlib.md5(
        content,
        usedforsecurity=False,
    ).hexdigest()

    verification = verify_expected_file(
        path,
        expected_bytes=len(content),
        expected_md5=expected_md5,
        gzip_required=True,
    )

    assert verification.valid is True
    assert verification.observed_bytes == len(content)
    assert verification.observed_md5 == expected_md5
    assert verification.gzip_valid is True
    assert verification.sha256 == hashlib.sha256(content).hexdigest()
    assert verification.errors == ()


def test_verify_gzip_rejects_truncated_stream(
    tmp_path: Path,
) -> None:
    path = tmp_path / "truncated.fastq.gz"

    with gzip.open(path, "wb") as handle:
        handle.write(b"@read1\nACGT\n+\nIIII\n")

    path.write_bytes(path.read_bytes()[:-4])

    try:
        verify_gzip(path)
    except (EOFError, gzip.BadGzipFile):
        pass
    else:
        raise AssertionError("truncated gzip stream was accepted")
