# Spec: RNA MVP profile expansion for rRNA depletion and long read RNA-seq

## Objective

Extend the existing human Bulk RNA-seq governance MVP from one frozen profile into a profile-based governance framework that can support:

1. `human_illumina_rrna_depletion_bulk_v1`
2. `human_longread_rnaseq_v1`

The first extension keeps the current short-read nf-core/rnaseq execution model and broad output shape. The second extension introduces a long-read path that must not be treated as a small parameter variant of STAR plus Salmon. The goal is to produce governed, traceable counts-like research assets while preserving the current MVP rule that large language models may orchestrate and explain, but deterministic tools perform analysis, QC, validation, and file generation.

Success means the project can classify uploaded or public GEO/SRA/ENA datasets into supported profiles, prepare profile-specific inputs, run or reject them deterministically, validate outputs with profile-appropriate rules, and write enough provenance for downstream cross-study T2D integration.

## Current architecture observed

The current repository is a Python package named `bulk-rnaseq-governance-mvp` with a Typer CLI entry point `rnaseq-mvp`. Definitions are stored as YAML under `definitions/`, loaded by `DefinitionRegistry`, validated by Pydantic models in `src/rnaseq_mvp/models.py`, and executed through preparation, Nextflow running, validation, review packaging, and state transitions.

Important current constraints:

- `DatasetDefinition` currently allows only `source_database: ENCODE`, `organism: Homo sapiens`, `assay: polyA plus RNA-seq`, `library_selection: Poly(A)+`, `read_layout: paired-end`, and `strandedness: reverse`.
- `SampleDefinition` currently requires exactly one `R1` and one `R2` file.
- `MethodDefinition` currently allows only `pipeline_name: nf-core/rnaseq`, `pipeline_version: 3.26.0`, `aligner: STAR`, `quantifier: Salmon`, `aggregation: tximport`, and `counts_measure_type: estimated_counts_unscaled`.
- `StageDefinition.stage_id` currently allows only `T2A` and `T2B`.
- `prepare.py` writes a short-read nf-core/rnaseq samplesheet with `sample,fastq_1,fastq_2,strandedness,seq_platform,seq_center`.
- `runner.py` always builds a command for `nf-core/rnaseq -r 3.26.0`.
- `validator.py` assumes short-read nf-core/rnaseq STAR-Salmon output paths, especially `star_salmon/salmon.merged.gene_counts.tsv`.

These constraints are useful for the first frozen MVP, but they must be generalized before adding new profiles.

## Assumptions

1. The reference profile remains `GRCh38.p14 + GENCODE Release 50` for both new human profiles unless a future profile explicitly changes reference scope.
2. `human_illumina_rrna_depletion_bulk_v1` should keep nf-core/rnaseq 3.26.0 initially, because the existing repository and server validation are already pinned to that version.
3. `human_longread_rnaseq_v1` should initially target gene-level counts only, not full isoform discovery or transcript novelty calling.
4. Oxford Nanopore and PacBio long-read data should be accepted only after platform and protocol are explicit in metadata.
5. Long-read support may use a different pipeline or a custom deterministic wrapper; it should not reuse the short-read STAR-Salmon validator.
6. GEO public data ingestion remains a catalog-first process: metadata are collected, profile eligibility is assigned, then only eligible datasets proceed to analysis.

## Source-grounded design notes

The short-read extension is compatible with nf-core/rnaseq because nf-core/rnaseq 3.26.0 documents STAR, RSEM, HISAT2, Salmon, gene/isoform counts, extensive QC, and a samplesheet with required `sample`, `fastq_1`, `fastq_2`, and `strandedness` columns plus optional `seq_platform` and `seq_center`. The same documentation supports `auto` strandedness inference and records strandedness results in MultiQC.

Official nf-core/rnaseq 3.26.0 usage: https://nf-co.re/rnaseq/3.26.0/docs/usage/

The long-read extension should be separated because nf-core/nanoseq uses a different samplesheet shape (`group`, `replicate`, `barcode`, `input_file`, `fasta`, `gtf`) and targets Nanopore demultiplexing, QC, and alignment rather than the short-read STAR-Salmon gene-count workflow.

Official nf-core/nanoseq usage: https://nf-co.re/nanoseq/docs/usage/

For a conservative long-read gene-count path, minimap2 is a credible alignment candidate because its official README documents spliced long-read RNA presets, including `-ax splice`, Nanopore direct RNA usage with `-uf -k14`, PacBio Iso-Seq usage with `splice:hq`, and annotated junction support.

Official minimap2 repository: https://github.com/lh3/minimap2

## Capability map

| Module id | Responsibility | Depends on |
|---|---|---|
| profile-model | Generalize definitions and schemas so profiles are not hard-coded to Poly(A)+ paired-end ENCODE | existing definitions |
| short-read-rrna-profile | Add rRNA depletion short-read profile, parameters, validation policy, and eligibility rules | profile-model |
| long-read-profile | Add long-read profile contract, input model, method definition, and output contract | profile-model |
| profile-aware-runner | Route stages to the correct command builder and result path expectations | profile-model, short-read-rrna-profile, long-read-profile |
| profile-aware-validator | Validate counts, QC metrics, and provenance using profile-specific artifact contracts | profile-aware-runner |
| documentation-and-adrs | Record scope, trade-offs, unsupported cases, and public data catalog classification rules | all modules |

Build order: profile-model -> short-read-rrna-profile -> long-read-profile -> profile-aware-runner -> profile-aware-validator -> documentation-and-adrs.

## Profile 1: human_illumina_rrna_depletion_bulk_v1

### Scope

This profile supports:

- Organism: `Homo sapiens`
- Data type: conventional Bulk RNA-seq
- Platform: Illumina short reads
- Library selection: `rRNA depletion`, `Ribo-Zero`, or equivalent controlled vocabulary term after metadata review
- Layout: single-end or paired-end
- Input: FASTQ `.fastq.gz` or `.fq.gz`
- Reference: `human_grch38_gencode_v50_primary`

This profile does not support:

- Single-cell RNA-seq
- Spatial transcriptomics
- small RNA or miRNA-seq
- non-human datasets
- long-read RNA-seq
- datasets where library selection cannot be established

### Method and pipeline

Recommended first implementation:

- Pipeline: `nf-core/rnaseq`
- Pipeline version: `3.26.0`
- Aligner: `STAR`
- Quantifier: `Salmon`
- Aggregation: `tximport`
- Counts measure type: `estimated_counts_unscaled`

This keeps execution near the current MVP but creates a separate method profile, for example:

`bulk_rnaseq_star_salmon_rrna_depletion_v1`

### Input contract

The samplesheet should remain compatible with nf-core/rnaseq:

```csv
sample,fastq_1,fastq_2,strandedness,seq_platform,seq_center
SAMPLE_001,/path/R1.fastq.gz,/path/R2.fastq.gz,auto,ILLUMINA,unknown
SAMPLE_002,/path/R1.fastq.gz,,auto,ILLUMINA,unknown
```

Definition model changes:

- `source_database` must allow `GEO`, `SRA`, `ENA`, `ENCODE`, and `private_upload`.
- `library_selection` must allow controlled values such as `Poly(A)+`, `rRNA depletion`, `total RNA`, and `unknown`, while profile eligibility rejects unsupported or unknown values.
- `read_layout` must allow `single-end` and `paired-end`.
- `strandedness` must allow `forward`, `reverse`, `unstranded`, and `auto`.
- `SampleDefinition` must allow either one `R1` for single-end or paired `R1` and `R2`.

### Output contract

The primary output remains gene-level estimated counts:

- `gene_counts_raw_estimated.tsv`
- `gene_counts_scaled.tsv`
- `gene_counts_length_scaled.tsv`
- `gene_tpm.tsv`
- `SummarizedExperiment.rds`
- `multiqc_report.html`
- `validation_report.json`
- `qc_metrics.tsv`
- `run_provenance.json`

The internal nf-core path may remain `star_salmon/salmon.merged.gene_counts.tsv`, but the governance package should publish a stable asset alias named `gene_counts_raw_estimated.tsv`.

### QC and validation policy

The rRNA depletion profile should not silently reuse the Poly(A)+ interpretation. It should:

- Keep mapping validation, but record whether the metric is STAR unique mapping, total mapping, or another MultiQC metric.
- Treat rRNA percent as a warning metric, not an automatic failure unless extremely high or project-specific.
- Record mitochondrial percent but interpret it by tissue and study context.
- Require strandedness inference to be consistent with declared library protocol, or use `auto` and report the inferred result.
- Add gene assignment rate or featureCounts assignment metrics when available.
- Add warnings for high intronic or intergenic fractions when the metric is available, but avoid forcing a universal threshold in v1.

Suggested validation profile:

`bulk_rnaseq_rrna_depletion_v1`

Initial thresholds should be explicit as MVP policy, not universal biology standards.

## Profile 2: human_longread_rnaseq_v1

### Scope

This profile supports:

- Organism: `Homo sapiens`
- Data type: long-read RNA-seq
- Platform: Oxford Nanopore or PacBio
- Protocol: cDNA, direct RNA, Iso-Seq, Kinnex/Iso-Seq, or explicitly reviewed equivalent
- Input: demultiplexed FASTQ `.fastq.gz` / `.fq.gz` or aligned BAM when allowed by the selected deterministic workflow
- Output level for v1: gene-level counts only

This profile does not support in v1:

- de novo isoform discovery as a governed primary output
- RNA modification calling
- allele-specific expression
- fusion detection
- mixed short-read and long-read co-analysis in one run
- single-cell long-read experiments

### Method options

Two candidate approaches exist.

Option A: custom conservative long-read gene-count workflow

```text
FASTQ
-> long-read QC
-> minimap2 splice-aware alignment
-> sorted/indexed BAM
-> gene-level assignment
-> gene_counts_raw.tsv
-> QC and validation
```

Pros:

- Smaller first implementation
- Easier to map outputs into the current CDM
- Clearer validation target: gene-level counts

Cons:

- Less isoform-aware
- Requires maintaining more custom workflow logic

Option B: nf-core/nanoseq-based workflow

Pros:

- Existing nf-core execution and reporting model
- Supports Nanopore demultiplexing, QC, alignment, and protocol options

Cons:

- Different samplesheet and outputs
- More disruptive to the current runner and validator
- Primarily Nanopore-oriented; PacBio support and gene-level count contract must be verified before acceptance

Recommended v1 decision: implement Option A as the minimal governed gene-count profile, while documenting nf-core/nanoseq as a future candidate for a fuller Nanopore workflow.

Suggested method profile:

`longread_rnaseq_minimap2_gene_counts_v1`

### Input contract

Long-read samples require a different samplesheet or manifest:

```csv
sample,input_file,platform,protocol,strandedness,reference_profile_id
SAMPLE_001,/path/sample.fastq.gz,ONT,cDNA,auto,human_grch38_gencode_v50_primary
SAMPLE_002,/path/sample.bam,PacBio,IsoSeq,unknown,human_grch38_gencode_v50_primary
```

Required metadata:

- `sample`
- `input_file`
- `platform`
- `protocol`
- `organism`
- `reference_profile_id`
- `source_database`
- `file checksum`

Recommended metadata:

- `basecaller`
- `chemistry`
- `read_n50`
- `mean_read_length`
- `total_bases`
- `run_accession`
- `sample_accession`

### Output contract

Stable governed outputs:

- `gene_counts_raw.tsv`
- `alignment_summary.tsv`
- `longread_qc_metrics.tsv`
- `multiqc_report.html` if available
- `validation_report.json`
- `run_provenance.json`
- `reference_manifest.tsv`
- `input_manifest.tsv`

Optional outputs:

- `sample.sorted.bam`
- `sample.sorted.bam.bai`
- `read_length_distribution.tsv`
- `junction_support.tsv`

`gene_counts_raw.tsv` must not be labeled as Salmon estimated counts. The `measure_type` should be distinct, for example:

`assigned_longread_gene_counts`

### QC and validation policy

Suggested validation profile:

`longread_rnaseq_gene_counts_v1`

Core validation:

- input file exists and checksum matches
- reference FASTA and GTF are traceable
- BAM exists and is indexed when alignment is run
- gene counts table contains `gene_id`, `gene_name`, and expected sample columns
- counts are numeric, finite, non-negative, and gene identifiers trace to GTF
- per-sample alignment or assignment metrics are present

QC metrics should include:

- total reads
- total bases
- read N50 or read length distribution summary
- alignment rate
- primary alignment rate when available
- gene assignment rate
- mitochondrial read fraction when computable
- rRNA fraction when computable

Thresholds should be warning-oriented in v1 because long-read RNA-seq quality varies strongly by platform, chemistry, protocol, and basecaller.

## Data model changes

### New profile taxonomy

Introduce explicit profile fields instead of encoding all constraints in literals:

- `analysis_profile_id`
- `organism`
- `assay_family`
- `read_technology`
- `read_layout`
- `library_selection`
- `platform`
- `protocol`
- `supported_input_kinds`
- `method_profile_id`
- `validation_policy_id`
- `output_contract_id`

### Definition model changes

Recommended changes:

- Split strict frozen definitions from extensible profile definitions.
- Add `AnalysisProfileDefinition` or extend `MethodDefinition` with a profile contract.
- Replace many Pydantic `Literal[...]` constraints with controlled vocabularies plus profile-specific eligibility validation.
- Allow `FileDefinition.role` values beyond `R1` and `R2`, such as `FASTQ`, `BAM`, and `FAST5_DIR` if needed later.
- Allow stage ids beyond `T2A` and `T2B`.
- Keep existing T2A/T2B definitions frozen by tests so current behavior cannot drift.

## Runner changes

Create profile-aware command builders:

- `build_short_read_rnaseq_command`
- `build_longread_gene_counts_command`

The current `build_nextflow_command` should become one implementation behind a dispatcher keyed by `method_profile_id` or `pipeline_name`.

For `human_illumina_rrna_depletion_bulk_v1`, the dispatcher should still use nf-core/rnaseq.

For `human_longread_rnaseq_v1`, the dispatcher should initially call a deterministic long-read workflow wrapper or a pinned pipeline command once selected. The v1 spec does not authorize mixing this into the STAR-Salmon command path.

## Validator changes

Create output-contract-aware validation:

- Short-read STAR-Salmon output contract:
  - `star_salmon/salmon.merged.gene_counts.tsv`
  - `star_salmon/salmon.merged.gene_tpm.tsv`
  - `multiqc/star_salmon/multiqc_report.html`

- Long-read gene-count output contract:
  - `gene_counts_raw.tsv` or configured path
  - alignment or assignment metrics
  - profile-specific QC metrics

Shared counts validation can remain a common function as long as it receives:

- counts path
- expected sample ids
- GTF path
- measure type
- profile id

## Documentation and ADRs

Write one ADR after spec approval:

`docs/decisions/ADR-001-profile-based-rnaseq-governance.md`

Decision to record:

- Keep current Poly(A)+ profile frozen.
- Add profile-aware governance rather than mutating the original MVP in place.
- Treat rRNA depletion as a short-read profile variant.
- Treat long-read RNA-seq as a separate method family with a conservative gene-count v1.

## Commands

Current repository commands:

```bash
uv run ruff check .
uv run pytest
uv run rnaseq-mvp --help
```

Server execution remains profile-dependent and must use pinned tools and containers.

## Testing strategy

Add tests in layers:

1. Definition tests
   - existing T2A/T2B definitions still load unchanged
   - new profile definitions load
   - invalid profile/data combinations are rejected

2. Preparation tests
   - paired short-read samplesheet generation
   - single-end short-read samplesheet generation
   - long-read samplesheet or manifest generation

3. Runner tests
   - short-read rRNA profile dispatches to nf-core/rnaseq
   - long-read profile does not dispatch to STAR-Salmon path
   - unsupported profile fails with clear error

4. Validator tests
   - current STAR-Salmon validation still passes fixtures
   - rRNA depletion policy changes strandedness and rRNA interpretation without weakening counts validation
   - long-read counts validator accepts a minimal valid gene-count fixture

5. Integration tests
   - dry-run or stubbed executor for each profile
   - no full public-data run required in unit test suite

## Boundaries

Always do:

- Preserve current T2A/T2B behavior.
- Keep GRCh38.p14 and GENCODE Release 50 checksums traceable.
- Preserve deterministic validation and explicit `measure_type`.
- Reject unknown or unsupported metadata instead of silently coercing it.
- Keep public GEO/SRA/ENA data in a catalog state until human review confirms profile eligibility.

Ask first:

- Adding a new external workflow dependency.
- Pinning a long-read pipeline version.
- Changing server resource requirements.
- Changing thresholds from warning to failure.
- Accepting author-provided counts without FASTQ reprocessing.

Never do:

- Mix Poly(A)+, rRNA depletion, and long-read counts without recording profile and batch variables.
- Label long-read assigned counts as Salmon estimated counts.
- Treat missing library selection as Poly(A)+ or rRNA depletion by assumption.
- Replace deterministic QC with LLM judgment.
- Silently reuse short-read validator paths for long-read outputs.

## Success criteria

The profile expansion is complete when:

- Existing T2A/T2B tests pass unchanged.
- A new rRNA depletion profile can be represented, prepared, run through the short-read dispatcher, and validated with rRNA-specific policy.
- A new long-read profile can be represented and prepared with a distinct method profile and output contract.
- Unsupported profile/data combinations produce actionable errors.
- Documentation explains which GEO T2D datasets are ready for current MVP, waiting for rRNA profile, waiting for long-read profile, external counts only, out of scope, or needing manual review.
- Output assets record `analysis_profile_id`, `method_profile_id`, `validation_policy_id`, `reference_profile_id`, and `measure_type`.

## Open questions

1. Should `human_longread_rnaseq_v1` target Oxford Nanopore only for v1, or include PacBio Iso-Seq in the same profile?
2. Should long-read v1 use a custom minimap2 plus gene assignment wrapper, or adopt nf-core/nanoseq despite its different input and output model?
3. For rRNA depletion datasets, should high rRNA fraction ever fail validation in v1, or only warn pending tissue- and protocol-specific calibration?
4. Should profile eligibility live only in Python validation, or also in the public GEO catalog workbook as controlled status columns?
5. Should published outputs be copied to stable alias names immediately after pipeline completion, or only in a later review/package step?

