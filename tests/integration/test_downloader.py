from pathlib import Path

import httpx
import pytest

from rnaseq_mvp.downloader import download_to_part


def test_download_to_part_resumes_with_range(tmp_path: Path) -> None:
    destination = tmp_path / "reads.fastq.gz"
    part = tmp_path / "reads.fastq.gz.part"
    part.write_bytes(b"abc")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=3-"
        return httpx.Response(206, content=b"def")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = download_to_part(
        "https://example.org/reads.fastq.gz",
        destination,
        client,
        expected_bytes=6,
    )

    assert result.resumed is True
    assert result.bytes_on_disk == 6
    assert result.http_status == 206
    assert part.read_bytes() == b"abcdef"
    assert not destination.exists()


def test_download_restarts_when_server_ignores_range(tmp_path: Path) -> None:
    destination = tmp_path / "reads.fastq.gz"
    part = tmp_path / "reads.fastq.gz.part"
    part.write_bytes(b"stale")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=5-"
        return httpx.Response(200, content=b"complete")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = download_to_part(
        "https://example.org/reads.fastq.gz",
        destination,
        client,
        expected_bytes=8,
    )

    assert result.resumed is False
    assert result.http_status == 200
    assert part.read_bytes() == b"complete"


def test_download_rejects_non_https_url(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: None))

    with pytest.raises(ValueError, match="HTTPS"):
        download_to_part(
            "http://example.org/reads.fastq.gz",
            tmp_path / "reads.fastq.gz",
            client,
            expected_bytes=10,
        )
