from pathlib import Path

from scripts.create_longread_smoke_assets import create_assets


def test_create_longread_smoke_assets(tmp_path: Path) -> None:
    create_assets(tmp_path)

    fastq = tmp_path / "LONG_SMOKE.fastq"
    fasta = tmp_path / "reference.fa"
    assert fastq.is_file()
    assert fasta.is_file()
    assert (tmp_path / "annotation.gtf").is_file()
    samplesheet = tmp_path / "longread_samplesheet.csv"
    assert samplesheet.is_file()
    assert samplesheet.read_text(encoding="utf-8").splitlines()[0] == (
        "sample,input_file,platform,protocol,strandedness,reference_profile_id"
    )
    fastq_lines = fastq.read_text(encoding="utf-8").splitlines()
    read_sequence = fastq_lines[1]
    quality = fastq_lines[3]
    assert len(read_sequence) >= 500
    assert len(quality) == len(read_sequence)
    assert read_sequence in fasta.read_text(encoding="utf-8")
