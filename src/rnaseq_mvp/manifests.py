from __future__ import annotations

import csv
import io
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rnaseq_mvp.checksums import hash_file


def _temporary_path(path: Path) -> Path:
    return path.with_suffix(f"{path.suffix}.tmp")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path)

    try:
        with temporary.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(
    path: Path,
    value: Mapping[str, Any],
) -> None:
    content = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    _atomic_write_text(path, f"{content}\n")


def _tsv_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )

    return str(value)


def write_tsv(
    path: Path,
    rows: Sequence[BaseModel],
) -> None:
    if not rows:
        raise ValueError("cannot write TSV without rows")

    columns = tuple(type(rows[0]).model_fields)
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(columns)

    for row in rows:
        row_columns = tuple(type(row).model_fields)

        if row_columns != columns:
            raise ValueError("all TSV rows must use the same model")

        values = row.model_dump(mode="json")
        writer.writerow(
            [_tsv_value(values[column]) for column in columns]
        )

    _atomic_write_text(path, buffer.getvalue())


def manifest_sha256(path: Path) -> str:
    return hash_file(path, "sha256")
