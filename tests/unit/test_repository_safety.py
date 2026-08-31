from pathlib import Path

from scripts.check_repository_safety import scan_repository


def test_safety_scan_rejects_fastq_and_private_key(tmp_path: Path) -> None:
    (tmp_path / "sample.fastq.gz").write_bytes(b"not real fastq")
    (tmp_path / "id_rsa.pem").write_text("PRIVATE KEY", encoding="utf-8")

    findings = scan_repository(tmp_path)

    assert {finding.rule for finding in findings} == {
        "forbidden_data",
        "secret_file",
    }


def test_safety_scan_rejects_patient_identifier_header(tmp_path: Path) -> None:
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "patients.csv").write_text(
        "patient_id,value\nP001,1\n", encoding="utf-8"
    )

    findings = scan_repository(tmp_path)

    assert [finding.rule for finding in findings] == ["patient_identifier"]
