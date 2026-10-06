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


def test_expansion_method_profiles_are_registered() -> None:
    registry = DefinitionRegistry.load(REPO_ROOT / "definitions")

    rrna = registry.method("bulk_rnaseq_star_salmon_rrna_depletion_v1")
    longread = registry.method("longread_rnaseq_minimap2_gene_counts_v1")

    assert rrna.method_family == "shortread_star_salmon"
    assert rrna.counts_measure_type == "estimated_counts_unscaled"
    assert longread.method_family == "longread_gene_counts"
    assert longread.counts_measure_type == "assigned_longread_gene_counts"


def test_expansion_validation_policies_are_registered() -> None:
    registry = DefinitionRegistry.load(REPO_ROOT / "definitions")

    rrna = registry.validation("bulk_rnaseq_rrna_depletion_v1")
    longread = registry.validation("longread_rnaseq_gene_counts_v1")

    assert rrna.rrna_warn_percent == 30.0
    assert longread.mapping_pass_percent == 60.0
