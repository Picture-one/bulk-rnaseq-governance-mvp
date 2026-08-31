from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    root: Path
    raw: Path
    reference: Path
    work: Path
    results: Path
    runs: Path
    logs: Path
    manifests: Path
    validation: Path
    quarantine: Path
    release: Path

    @classmethod
    def from_root(cls, root: Path) -> WorkspacePaths:
        resolved = root.expanduser().resolve()

        return cls(
            root=resolved,
            raw=resolved / "raw",
            reference=resolved / "reference",
            work=resolved / "work",
            results=resolved / "results",
            runs=resolved / "runs",
            logs=resolved / "logs",
            manifests=resolved / "manifests",
            validation=resolved / "validation",
            quarantine=resolved / "quarantine",
            release=resolved / "release",
        )
