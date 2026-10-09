from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx


class PublicDownloadError(RuntimeError):
    """Raised when public FASTQ download or verification fails."""


@dataclass(frozen=True)
class PublicFastqFile:
    file_name: str
    download_url: str
    expected_bytes: int
    expected_md5: str
    local_path: Path


@dataclass(frozen=True)
class PublicDownloadFileResult:
    file_name: str
    status: str
    attempts: int
    local_path: Path


@dataclass(frozen=True)
class PublicDownloadResult:
    manifest_tsv: Path
    file_count: int
    downloaded_count: int
    reused_count: int
    repaired_count: int
    results: list[PublicDownloadFileResult]


Downloader = Callable[[str, Path, float], None]


def download_public_fastqs(
    *,
    manifest_tsv: Path,
    max_attempts: int = 3,
    timeout_seconds: float = 120.0,
    downloader: Downloader | None = None,
) -> PublicDownloadResult:
    """Download all FASTQ files listed in a public manifest and verify them.

    Existing valid files are reused. Existing invalid files are deleted and
    downloaded again. Each file is verified by both byte size and MD5.
    """
    manifest_tsv = Path(manifest_tsv)
    if max_attempts < 1:
        raise PublicDownloadError("max_attempts must be at least 1")
    if not manifest_tsv.exists():
        raise PublicDownloadError(f"FASTQ manifest not found: {manifest_tsv}")

    records = read_fastq_manifest(manifest_tsv)
    if not records:
        raise PublicDownloadError(f"FASTQ manifest is empty: {manifest_tsv}")

    fetch = downloader or _download_with_httpx
    results: list[PublicDownloadFileResult] = []
    downloaded_count = 0
    reused_count = 0
    repaired_count = 0

    for record in records:
        status, attempts, repaired = _ensure_fastq_file(
            record,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            downloader=fetch,
        )
        if status == "reused":
            reused_count += 1
        else:
            downloaded_count += 1
        if repaired:
            repaired_count += 1
        results.append(
            PublicDownloadFileResult(
                file_name=record.file_name,
                status=status,
                attempts=attempts,
                local_path=record.local_path,
            )
        )

    return PublicDownloadResult(
        manifest_tsv=manifest_tsv,
        file_count=len(records),
        downloaded_count=downloaded_count,
        reused_count=reused_count,
        repaired_count=repaired_count,
        results=results,
    )


def read_fastq_manifest(manifest_tsv: Path) -> list[PublicFastqFile]:
    required = {
        "file_name",
        "download_url",
        "expected_bytes",
        "expected_md5",
        "local_path",
    }
    with Path(manifest_tsv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise PublicDownloadError(f"Manifest has no header: {manifest_tsv}")
        missing = required - set(reader.fieldnames)
        if missing:
            raise PublicDownloadError(
                f"Manifest is missing columns: {sorted(missing)}"
            )
        return [_row_to_fastq_file(row) for row in reader]


def verify_fastq_file(record: PublicFastqFile) -> tuple[bool, str]:
    path = record.local_path
    if not path.exists():
        return False, "missing"
    observed_bytes = path.stat().st_size
    if observed_bytes != record.expected_bytes:
        return (
            False,
            f"size mismatch: expected {record.expected_bytes}, got {observed_bytes}",
        )
    observed_md5 = md5_file(path)
    if observed_md5 != record.expected_md5:
        return (
            False,
            f"md5 mismatch: expected {record.expected_md5}, got {observed_md5}",
        )
    return True, "valid"


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_fastq_file(
    record: PublicFastqFile,
    *,
    max_attempts: int,
    timeout_seconds: float,
    downloader: Downloader,
) -> tuple[str, int, bool]:
    valid, reason = verify_fastq_file(record)
    if valid:
        return "reused", 0, False

    repaired = record.local_path.exists()
    if repaired:
        record.local_path.unlink()

    last_error = reason
    for attempt in range(1, max_attempts + 1):
        part_path = record.local_path.with_name(record.local_path.name + ".part")
        if part_path.exists():
            part_path.unlink()
        record.local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            downloader(record.download_url, part_path, timeout_seconds)
            part_path.replace(record.local_path)
        except Exception as exc:  # noqa: BLE001 - preserve retry context for CLI users
            last_error = str(exc)
            if part_path.exists():
                part_path.unlink()
            continue

        valid, reason = verify_fastq_file(record)
        if valid:
            return "downloaded", attempt, repaired
        last_error = reason
        if record.local_path.exists():
            record.local_path.unlink()

    raise PublicDownloadError(
        f"Failed to download verified FASTQ after {max_attempts} attempts: "
        f"{record.file_name}; last error: {last_error}"
    )


def _download_with_httpx(url: str, destination: Path, timeout_seconds: float) -> None:
    timeout = httpx.Timeout(timeout_seconds, connect=30.0)
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def _row_to_fastq_file(row: dict[str, str]) -> PublicFastqFile:
    file_name = row["file_name"].strip()
    download_url = row["download_url"].strip()
    expected_md5 = row["expected_md5"].strip().lower()
    local_path = Path(row["local_path"].strip())
    try:
        expected_bytes = int(row["expected_bytes"].strip())
    except ValueError as exc:
        raise PublicDownloadError(
            f"Invalid expected_bytes for {file_name}: {row['expected_bytes']!r}"
        ) from exc

    if not file_name:
        raise PublicDownloadError("Manifest row has empty file_name")
    if not download_url:
        raise PublicDownloadError(f"{file_name}: empty download_url")
    if expected_bytes <= 0:
        raise PublicDownloadError(f"{file_name}: expected_bytes must be positive")
    if not expected_md5:
        raise PublicDownloadError(f"{file_name}: empty expected_md5")
    if not local_path.name:
        raise PublicDownloadError(f"{file_name}: invalid local_path")

    return PublicFastqFile(
        file_name=file_name,
        download_url=download_url,
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
        local_path=local_path,
    )
