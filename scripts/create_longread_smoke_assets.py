from __future__ import annotations

import argparse
from pathlib import Path


def create_assets(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fastq = output_dir / "LONG_SMOKE.fastq"
    fasta = output_dir / "reference.fa"
    gtf = output_dir / "annotation.gtf"
    samplesheet = output_dir / "longread_samplesheet.csv"
    sequence = "ACGT" * 200
    quality = "I" * len(sequence)

    fastq.write_text(
        "@read1\n"
        f"{sequence}\n"
        "+\n"
        f"{quality}\n",
        encoding="utf-8",
    )
    fasta.write_text(
        ">chr1\n"
        f"{sequence}\n",
        encoding="utf-8",
    )
    gtf.write_text(
        f'chr1\tSMOKE\tgene\t1\t{len(sequence)}\t.\t+\t.\tgene_id "ENSGSMOKE000001.1"; '
        'gene_name "SMOKE1";\n'
        f'chr1\tSMOKE\texon\t1\t{len(sequence)}\t.\t+\t.\tgene_id "ENSGSMOKE000001.1"; '
        'gene_name "SMOKE1"; transcript_id "ENSTSMOKE000001.1";\n',
        encoding="utf-8",
    )
    samplesheet.write_text(
        "sample,input_file,platform,protocol,strandedness,reference_profile_id\n"
        f"LONG_SMOKE,{fastq.resolve()},ONT,cDNA,auto,human_grch38_gencode_v50_primary\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create tiny ONT long-read smoke-test assets."
    )
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    create_assets(args.output_dir)
    print(args.output_dir)


if __name__ == "__main__":
    main()
