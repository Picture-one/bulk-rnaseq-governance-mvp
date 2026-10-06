import json
from pathlib import Path

from rnaseq_mvp.longread import (
    LongreadPostprocessInput,
    run_longread_workflow,
    write_longread_postprocess_outputs,
)


class FakeLongreadExecutor:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], stdout_path: Path | None = None) -> None:
        self.commands.append(command)
        if command[0] == "seqkit":
            assert stdout_path is not None
            stdout_path.write_text(
                "file\tformat\ttype\tnum_seqs\tsum_len\tmin_len\tavg_len\tmax_len\n"
                "sample.fastq.gz\tFASTQ\tDNA\t2\t16\t8\t8\t8\n",
                encoding="utf-8",
            )
        elif command[0] == "minimap2":
            assert stdout_path is not None
            stdout_path.write_text("@HD\tVN:1.6\n", encoding="utf-8")
        elif command[:2] == ["samtools", "sort"]:
            output = Path(command[command.index("-o") + 1])
            output.write_text("BAM\n", encoding="utf-8")
        elif command[:2] == ["samtools", "index"]:
            Path(f"{command[2]}.bai").write_text("BAI\n", encoding="utf-8")
        elif command[:2] == ["samtools", "flagstat"]:
            assert stdout_path is not None
            stdout_path.write_text(
                "10 + 0 in total (QC-passed reads + QC-failed reads)\n"
                "8 + 0 mapped (80.00% : N/A)\n",
                encoding="utf-8",
            )
        elif command[0] == "featureCounts":
            output = Path(command[command.index("-o") + 1])
            output.write_text(
                "# Program:featureCounts\n"
                "Geneid\tChr\tStart\tEnd\tStrand\tLength\tLONG_SAMPLE.sorted.bam\n"
                "ENSG000001.1\tchr1\t1\t8\t+\t8\t2\n",
                encoding="utf-8",
            )
            output.with_name(f"{output.name}.summary").write_text(
                "Status\tLONG_SAMPLE.sorted.bam\n"
                "Assigned\t2\n"
                "Unassigned_Unmapped\t0\n",
                encoding="utf-8",
            )


def test_write_longread_postprocess_outputs(tmp_path: Path) -> None:
    output = write_longread_postprocess_outputs(
        LongreadPostprocessInput(
            results_dir=tmp_path,
            sample_ids=["LONG_SAMPLE"],
            gene_rows=[
                {
                    "gene_id": "ENSG000001.1",
                    "gene_name": "GENE1",
                    "LONG_SAMPLE": 12,
                }
            ],
            alignment_rows=[
                {
                    "sample_id": "LONG_SAMPLE",
                    "alignment_rate": 88.5,
                    "primary_alignment_rate": 86.0,
                }
            ],
            qc_rows=[
                {
                    "sample_id": "LONG_SAMPLE",
                    "metric": "total_reads",
                    "value": 1000,
                }
            ],
            provenance={
                "method_profile_id": "longread_rnaseq_minimap2_gene_counts_v1",
                "measure_type": "assigned_longread_gene_counts",
            },
        )
    )

    assert output.counts_path == tmp_path / "longread" / "gene_counts_raw.tsv"
    assert output.alignment_summary_path.is_file()
    assert output.qc_metrics_path.is_file()
    assert output.provenance_path.is_file()
    assert output.counts_path.read_text(encoding="utf-8").splitlines() == [
        "gene_id\tgene_name\tLONG_SAMPLE",
        "ENSG000001.1\tGENE1\t12",
    ]
    provenance = json.loads(output.provenance_path.read_text(encoding="utf-8"))
    assert provenance["measure_type"] == "assigned_longread_gene_counts"


def test_run_longread_workflow_creates_governed_outputs(tmp_path: Path) -> None:
    fastq = tmp_path / "sample.fastq.gz"
    fasta = tmp_path / "reference.fa"
    gtf = tmp_path / "annotation.gtf"
    samplesheet = tmp_path / "longread_samplesheet.csv"
    outdir = tmp_path / "results"
    fastq.write_text("@r1\nACGTACGT\n+\nIIIIIIII\n@r2\nACGTACGT\n+\nIIIIIIII\n", encoding="utf-8")
    fasta.write_text(">chr1\nACGTACGT\n", encoding="utf-8")
    gtf.write_text(
        'chr1\tTEST\tgene\t1\t8\t.\t+\t.\tgene_id "ENSG000001.1"; gene_name "GENE1";\n',
        encoding="utf-8",
    )
    samplesheet.write_text(
        "sample,input_file,platform,protocol,strandedness,reference_profile_id\n"
        f"LONG_SAMPLE,{fastq},ONT,cDNA,auto,human_grch38_gencode_v50_primary\n",
        encoding="utf-8",
    )
    executor = FakeLongreadExecutor()

    result = run_longread_workflow(
        samplesheet=samplesheet,
        fasta=fasta,
        gtf=gtf,
        outdir=outdir,
        threads=2,
        executor=executor,
    )

    assert result.counts_path.read_text(encoding="utf-8").splitlines() == [
        "gene_id\tgene_name\tLONG_SAMPLE",
        "ENSG000001.1\tGENE1\t2",
    ]
    assert result.alignment_summary_path.is_file()
    assert result.qc_metrics_path.is_file()
    provenance = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    assert provenance["method_profile_id"] == "longread_rnaseq_minimap2_gene_counts_v1"
    assert any(command[0] == "minimap2" for command in executor.commands)
    assert any(command[0] == "featureCounts" for command in executor.commands)
