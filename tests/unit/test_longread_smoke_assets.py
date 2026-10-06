from pathlib import Path

from scripts.create_longread_smoke_assets import create_assets


def test_create_longread_smoke_assets(tmp_path: Path) -> None:
    create_assets(tmp_path)

    assert (tmp_path / "LONG_SMOKE.fastq").is_file()
    assert (tmp_path / "reference.fa").is_file()
    assert (tmp_path / "annotation.gtf").is_file()
    samplesheet = tmp_path / "longread_samplesheet.csv"
    assert samplesheet.is_file()
    assert samplesheet.read_text(encoding="utf-8").splitlines()[0] == (
        "sample,input_file,platform,protocol,strandedness,reference_profile_id"
    )
