from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MAX_ATTEMPTS = 5


class DownloadError(RuntimeError):
    """Raised when an input cannot be downloaded safely."""


@dataclass(frozen=True)
class DownloadResult:
    part_path: Path
    bytes_on_disk: int
    resumed: bool
    http_status: int | None


def _part_path(destination: Path) -> Path:
    return destination.with_suffix(f"{destination.suffix}.part")


def download_to_part(
    url: str,
    destination: Path,
    client: httpx.Client,
    expected_bytes: int,
) -> DownloadResult:
    if httpx.URL(url).scheme != "https":
        raise ValueError("download URL must use HTTPS")
    if expected_bytes <= 0:
        raise ValueError("expected_bytes must be positive")

    part = _part_path(destination)
    part.parent.mkdir(parents=True, exist_ok=True)
    existing_bytes = part.stat().st_size if part.exists() else 0

    if existing_bytes > expected_bytes:
        raise DownloadError(
            f"partial file exceeds expected size: {existing_bytes} > {expected_bytes}"
        )
    if existing_bytes == expected_bytes:
        return DownloadResult(part, existing_bytes, True, None)

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        start_offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={start_offset}-"} if start_offset else {}

        try:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                server_resumed = start_offset > 0 and response.status_code == 206
                mode = "ab" if server_resumed else "wb"

                with part.open(mode) as handle:
                    for chunk in response.iter_bytes(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        if handle.tell() > expected_bytes:
                            raise DownloadError(
                                "downloaded file exceeds expected byte count"
                            )
                    handle.flush()
                    os.fsync(handle.fileno())

                return DownloadResult(
                    part_path=part,
                    bytes_on_disk=part.stat().st_size,
                    resumed=server_resumed,
                    http_status=response.status_code,
                )
        except DownloadError:
            raise
        except (httpx.HTTPError, OSError) as error:
            last_error = error
            if attempt == MAX_ATTEMPTS - 1:
                break
            time.sleep(min(2**attempt, 30))

    raise DownloadError(f"download failed after {MAX_ATTEMPTS} attempts") from last_error
