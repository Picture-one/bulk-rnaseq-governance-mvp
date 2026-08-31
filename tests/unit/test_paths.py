from pathlib import Path

from rnaseq_mvp.paths import WorkspacePaths


def test_workspace_paths_are_resolved_from_one_root(
    tmp_path: Path,
) -> None:
    paths = WorkspacePaths.from_root(tmp_path)

    assert paths.root == tmp_path.resolve()
    assert paths.raw == paths.root / "raw"
    assert paths.reference == paths.root / "reference"
    assert paths.work == paths.root / "work"
    assert paths.results == paths.root / "results"
    assert paths.runs == paths.root / "runs"
    assert paths.logs == paths.root / "logs"
    assert paths.manifests == paths.root / "manifests"
    assert paths.validation == paths.root / "validation"
    assert paths.quarantine == paths.root / "quarantine"
    assert paths.release == paths.root / "release"
