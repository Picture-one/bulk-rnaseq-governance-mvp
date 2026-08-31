from pathlib import Path

from rnaseq_mvp.definitions import DefinitionRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_t2a_frozen_files_and_reference() -> None:
    registry = DefinitionRegistry.load(REPO_ROOT / "definitions")
    stage = registry.stage("T2A")
    dataset = registry.dataset(stage.dataset_id)
    sample = next(
        sample
        for sample in dataset.samples
        if sample.sample_id == "K562_POLYA_REP1"
    )

    assert [
        (file.file_accession, file.role, file.expected_md5)
        for file in sample.files
    ] == [
        (
            "ENCFF001RED",
            "R1",
            "0e88b38c8d48806ee98929a5bad06fc4",
        ),
        (
            "ENCFF001RDZ",
            "R2",
            "3a25713488522b0ea8a4d9635b5afa41",
        ),
    ]

    reference = registry.reference(stage.reference_profile_id)

    assert reference.annotation_release == "50"
    assert reference.genome_build == "GRCh38"


def test_t2b_has_two_reverse_stranded_samples() -> None:
    registry = DefinitionRegistry.load(REPO_ROOT / "definitions")
    stage = registry.stage("T2B")

    assert stage.sample_ids == [
        "K562_POLYA_REP1",
        "K562_POLYA_REP2",
    ]
    assert registry.dataset(stage.dataset_id).strandedness == "reverse"
