from pathlib import Path

from rnaseq_mvp.checksums import hash_file


def test_hash_file_returns_known_digests(tmp_path: Path) -> None:
    path = tmp_path / "value.txt"
    path.write_bytes(b"abc")

    assert hash_file(path, "md5") == (
        "900150983cd24fb0d6963f7d28e17f72"
    )
    assert hash_file(path, "sha256") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
