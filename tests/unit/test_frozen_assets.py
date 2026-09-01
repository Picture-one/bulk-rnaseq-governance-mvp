import csv
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_T2A_PARAMS = {
    "aligner": "star_salmon",
    "gencode": True,
    "igenomes_ignore": True,
    "trimmer": "trimgalore",
    "min_trimmed_reads": 10000,
    "remove_ribo_rna": False,
    "with_umi": False,
    "gtf_group_features": "gene_id",
    "gtf_extra_attributes": "gene_name,gene_type",
    "featurecounts_group_type": "gene_type",
    "featurecounts_feature_type": "exon",
    "min_mapped_reads": 5,
    "skip_bbsplit": True,
    "skip_linting": False,
    "skip_trimming": False,
    "skip_quantification_merge": False,
    "skip_markduplicates": False,
    "skip_bigwig": True,
    "skip_stringtie": True,
    "skip_fastqc": False,
    "skip_preseq": True,
    "skip_dupradar": False,
    "skip_qualimap": False,
    "skip_rseqc": False,
    "skip_biotype_qc": False,
    "skip_deseq2_qc": True,
    "skip_multiqc": False,
    "save_reference": True,
    "save_trimmed": False,
    "save_align_intermeds": False,
}

SAMPLESHEET_HEADER = [
    "sample",
    "fastq_1",
    "fastq_2",
    "strandedness",
    "seq_platform",
    "seq_center",
]


def _load_yaml(relative_path: str) -> dict[str, object]:
    return yaml.safe_load(
        (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    )


def _load_samplesheet(
    relative_path: str,
) -> tuple[list[str] | None, list[dict[str, str]]]:
    with (REPO_ROOT / relative_path).open(
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def test_t2_params_are_frozen_and_portable() -> None:
    t2a = _load_yaml("configs/params/t2a.yaml")
    t2b = _load_yaml("configs/params/t2b.yaml")

    expected_t2b = {
        **EXPECTED_T2A_PARAMS,
        "skip_deseq2_qc": False,
    }

    assert t2a == EXPECTED_T2A_PARAMS
    assert t2b == expected_t2b

    runtime_keys = {"input", "outdir", "fasta", "gtf"}

    assert runtime_keys.isdisjoint(t2a)
    assert runtime_keys.isdisjoint(t2b)


def test_t2a_samplesheet_contains_one_frozen_pair() -> None:
    header, rows = _load_samplesheet("samplesheets/t2a.csv")

    assert header == SAMPLESHEET_HEADER
    assert rows == [
        {
            "sample": "K562_POLYA_REP1",
            "fastq_1": "raw/ENCSR000AEM/ENCFF001RED.fastq.gz",
            "fastq_2": "raw/ENCSR000AEM/ENCFF001RDZ.fastq.gz",
            "strandedness": "reverse",
            "seq_platform": "ILLUMINA",
            "seq_center": "CSHL",
        }
    ]


def test_t2b_samplesheet_contains_two_frozen_pairs() -> None:
    header, rows = _load_samplesheet("samplesheets/t2b.csv")

    assert header == SAMPLESHEET_HEADER
    assert rows == [
        {
            "sample": "K562_POLYA_REP1",
            "fastq_1": "raw/ENCSR000AEM/ENCFF001RED.fastq.gz",
            "fastq_2": "raw/ENCSR000AEM/ENCFF001RDZ.fastq.gz",
            "strandedness": "reverse",
            "seq_platform": "ILLUMINA",
            "seq_center": "CSHL",
        },
        {
            "sample": "K562_POLYA_REP2",
            "fastq_1": "raw/ENCSR000AEM/ENCFF001REG.fastq.gz",
            "fastq_2": "raw/ENCSR000AEM/ENCFF001REF.fastq.gz",
            "strandedness": "reverse",
            "seq_platform": "ILLUMINA",
            "seq_center": "CSHL",
        },
    ]
def test_arm64_wave_profile_is_frozen() -> None:
    config_path = (
        REPO_ROOT
        / "configs"
        / "profiles"
        / "server_docker_arm64.config"
    )
    config = config_path.read_text(encoding="utf-8")

    required_settings = [
        "docker.enabled = true",
        "wave.enabled = true",
        "wave.strategy = ['conda']",
        "process.arch = 'linux/arm64'",
        "cpus: 16",
        "memory: 60.GB",
        "time: 72.h",
    ]

    for setting in required_settings:
        assert setting in config
