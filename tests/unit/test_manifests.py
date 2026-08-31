import hashlib
from pathlib import Path

from pydantic import BaseModel

from rnaseq_mvp.manifests import (
    atomic_write_json,
    manifest_sha256,
    write_tsv,
)


class ExampleManifestRow(BaseModel):
    sample: str
    role: str
    expected_bytes: int


def test_atomic_write_json_is_sorted_and_leaves_no_tmp_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "report.json"

    atomic_write_json(
        destination,
        {
            "status": "PASS",
            "run_id": "T2A_20260901T013000Z",
        },
    )

    assert destination.read_text(encoding="utf-8") == (
        "{\n"
        '  "run_id": "T2A_20260901T013000Z",\n'
        '  "status": "PASS"\n'
        "}\n"
    )
    assert not destination.with_suffix(".json.tmp").exists()


def test_write_tsv_preserves_model_field_order_and_hash(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "input_manifest.tsv"
    rows = [
        ExampleManifestRow(
            sample="K562_POLYA_REP1",
            role="R1",
            expected_bytes=3,
        )
    ]

    write_tsv(destination, rows)

    expected = (
        "sample\trole\texpected_bytes\n"
        "K562_POLYA_REP1\tR1\t3\n"
    )

    assert destination.read_text(encoding="utf-8") == expected
    assert manifest_sha256(destination) == hashlib.sha256(
        expected.encode("utf-8")
    ).hexdigest()
    assert not destination.with_suffix(".tsv.tmp").exists()
