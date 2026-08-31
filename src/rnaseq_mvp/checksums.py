from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

HASH_CHUNK_SIZE = 8 * 1024 * 1024


@dataclass(frozen=True)
class FileVerification:
    path: Path
    expected_bytes: int
    observed_bytes: int | None
    expected_md5: str
    observed_md5: str | None
    sha256: str | None
    gzip_required: bool
    gzip_valid: bool | None
    valid: bool
    errors: tuple[str, ...]


def hash_file(
    path: Path,
    algorithm: Literal["md5", "sha256"],
) -> str:
    if algorithm == "md5":
        digest = hashlib.md5(usedforsecurity=False)
    elif algorithm == "sha256":
        digest = hashlib.sha256()
    else:
        raise ValueError(f"unsupported hash algorithm: {algorithm}")

    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)

    return digest.hexdigest()


def verify_gzip(path: Path) -> None:
    with gzip.open(path, "rb") as handle:
        while handle.read(HASH_CHUNK_SIZE):
            pass


def verify_expected_file(
    path: Path,
    expected_bytes: int,
    expected_md5: str,
    gzip_required: bool,
) -> FileVerification:
    if not path.is_file():
        return FileVerification(
            path=path,
            expected_bytes=expected_bytes,
            observed_bytes=None,
            expected_md5=expected_md5,
            observed_md5=None,
            sha256=None,
            gzip_required=gzip_required,
            gzip_valid=None,
            valid=False,
            errors=("file_not_found",),
        )

    observed_bytes = path.stat().st_size
    observed_md5 = hash_file(path, "md5")
    observed_sha256 = hash_file(path, "sha256")
    errors: list[str] = []

    if observed_bytes != expected_bytes:
        errors.append("byte_count_mismatch")

    if observed_md5 != expected_md5:
        errors.append("md5_mismatch")

    gzip_valid: bool | None = None

    if gzip_required:
        try:
            verify_gzip(path)
        except (EOFError, OSError):
            gzip_valid = False
            errors.append("gzip_invalid")
        else:
            gzip_valid = True

    return FileVerification(
        path=path,
        expected_bytes=expected_bytes,
        observed_bytes=observed_bytes,
        expected_md5=expected_md5,
        observed_md5=observed_md5,
        sha256=observed_sha256,
        gzip_required=gzip_required,
        gzip_valid=gzip_valid,
        valid=not errors,
        errors=tuple(errors),
    )
