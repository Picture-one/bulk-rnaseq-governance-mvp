# Spec: Long-read RNA-seq MVP with shared governance framework

## Objective

Build a separate `long-read RNA-seq MVP` for converting human long-read RNA-seq FASTQ data into governed gene-level counts, while reusing the existing Bulk RNA-seq MVP governance framework wherever it is genuinely shared.

The purpose is to avoid forcing Nanopore/PacBio long-read data through the current Illumina short-read `STAR + Salmon + tximport` workflow. Long-read RNA-seq should have its own deterministic analysis path from FASTQ to counts, but should share the platform-level governance concepts already built for the current MVP:

- project/run identity
- dataset and sample definitions
- file checksum and manifest tracking
- reference traceability
- state transitions
- validation reports
- review packaging
- result asset naming and provenance
- public database catalog eligibility

Success means a researcher or platform agent can submit eligible human long-read RNA-seq FASTQ files and receive traceable gene-level counts with long-read-specific QC and provenance, without confusing those counts with short-read Salmon estimated counts.

## Assumptions

1. The first long-read MVP is human-only: `Homo sapiens`.
2. The first reference remains `GRCh38.p14 + GENCODE Release 50`, matching the existing short-read governance reference unless a later long-read reference profile is approved.
3. The first output target is gene-level counts, not isoform discovery, novel transcript annotation, fusion detection, or RNA modification analysis.
4. The long-read MVP should support Oxford Nanopore first. PacBio Iso-Seq can be represented in the metadata model, but the first runnable workflow should be ONT-focused unless separately approved.
5. The current `bulk-rnaseq-governance-mvp` repository may host the shared governance library and the initial long-read runner, but the long-read workflow should remain a separate method family and not be hidden behind the existing `nf-core/rnaseq` runner.
6. LLM/agent logic may guide users, classify metadata, and explain errors, but must not replace deterministic QC, counting, or validation.

## Capability map

| Module id | Responsibility | Depends on |
|---|---|---|
| shared-governance-core | Extract or formalize reusable governance contracts: run state, manifests, reference traceability, validation report, review package, provenance | existing MVP |
| longread-input-contract | Define long-read dataset/sample/file metadata and manifest shape | shared-governance-core |
| longread-workflow-runner | Run a deterministic long-read FASTQ-to-counts workflow | longread-input-contract |
| longread-postprocessing | Normalize workflow outputs into stable governed assets | longread-workflow-runner |
| longread-validation | Validate counts, QC metrics, reference traceability, and provenance using long-read-specific rules | longread-postprocessing |
| longread-docs-and-example | Provide user-facing input template, output explanation, and one worked example | all modules |

Build order:

```text
shared-governance-core
→ longread-input-contract
→ longread-workflow-runner
→ longread-postprocessing
→ longread-validation
→ longread-docs-and-example
```

## Shared governance framework

The long-read MVP should reuse the following existing framework concepts:

| Shared component | Reuse decision |
|---|---|
| `DefinitionRegistry` | Reuse, but extend definitions so method families and stages are not short-read-only |
| `DatasetDefinition` / `SampleDefinition` | Reuse conceptually, but add long-read fields and stricter profile-specific validation |
| `WorkspacePaths` | Reuse |
| `StateStore` / run states | Reuse |
| `input_manifest.tsv` | Reuse shape where possible; add long-read-specific roles/fields only when needed |
| `reference_manifest.tsv` | Reuse |
| checksum verification | Reuse |
| `validation_report.json` | Reuse schema versioning concept; extend metrics |
| `qc_metrics.tsv` | Reuse tabular output concept; long-read metric names differ |
| `review package` | Reuse |
| public data catalog profile eligibility | Reuse concept; add long-read-specific controlled fields |

The long-read MVP should not reuse:

- `nf-core/rnaseq` as the execution pipeline
- STAR/Salmon output paths
- Salmon estimated counts measure type
- short-read mapping/rRNA thresholds without reinterpretation
- paired-end FASTQ assumptions

## Long-read input contract

### Supported v1 scope

Required:

- organism: `Homo sapiens`
- analysis profile: `human_longread_rnaseq_v1`
- source database: `GEO`, `SRA`, `ENA`, or `USER_UPLOAD`
- platform: `ONT`
- protocol: one of `cDNA`, `direct RNA`
- input kind: demultiplexed FASTQ `.fastq.gz` or `.fq.gz`
- one file per sample in v1, represented as role `R1` or `LONGREAD_FASTQ`
- reference profile: `human_grch38_gencode_v50_primary`

Explicitly out of scope for v1:

- single-cell long-read RNA-seq
- spatial long-read RNA-seq
- mixed short-read and long-read co-analysis
- raw signal-level FAST5/POD5 processing
- basecalling
- RNA modification calling
- fusion calling
- de novo isoform discovery as the primary governed output

### Long-read samplesheet

The long-read workflow should use a separate samplesheet instead of the short-read nf-core samplesheet:

```csv
sample,input_file,platform,protocol,strandedness,reference_profile_id
SAMPLE_001,/data/raw/SAMPLE_001.fastq.gz,ONT,cDNA,auto,human_grch38_gencode_v50_primary
SAMPLE_002,/data/raw/SAMPLE_002.fastq.gz,ONT,direct RNA,auto,human_grch38_gencode_v50_primary
```

Minimum metadata:

- `sample`
- `input_file`
- `platform`
- `protocol`
- `strandedness`
- `reference_profile_id`
- file size
- checksum
- source accession when public

Recommended metadata:

- basecaller
- chemistry
- flowcell
- kit
- mean read length
- read N50
- total reads
- total bases

## Long-read analysis workflow

The v1 workflow should be deterministic and conservative:

```text
FASTQ
→ long-read FASTQ QC
→ minimap2 splice-aware genome alignment
→ sorted/indexed BAM
→ gene-level read assignment against GENCODE GTF
→ raw gene counts table
→ long-read QC metrics
→ governed output package
```

Recommended first method profile:

```yaml
method_profile_id: longread_rnaseq_minimap2_gene_counts_v1
method_family: longread_gene_counts
pipeline_name: custom-longread-gene-counts
pipeline_version: 0.1.0
aligner: minimap2
quantifier: featureCounts
aggregation: gene_assignment
counts_measure_type: assigned_longread_gene_counts
```

The exact counting tool can be finalized during implementation. The initial candidate is featureCounts in long-read-compatible mode, but the implementation plan must verify command-line support and document the pinned version before enabling real execution.

## Long-read output contract

The governed long-read output directory should contain:

```text
longread/gene_counts_raw.tsv
longread/alignment_summary.tsv
longread/longread_qc_metrics.tsv
longread/provenance.json
longread/sample.sorted.bam
longread/sample.sorted.bam.bai
```

Required stable published assets:

| Asset | Meaning |
|---|---|
| `gene_counts_raw.tsv` | Raw assigned gene-level counts |
| `longread_qc_metrics.tsv` | Long-read-specific QC metrics |
| `alignment_summary.tsv` | Per-sample alignment summary |
| `validation_report.json` | Governance validation result |
| `qc_metrics.tsv` | Normalized QC table |
| `input_manifest.tsv` | Input file traceability |
| `reference_manifest.tsv` | Reference file traceability |
| `run_provenance.json` | Tool versions, command, parameters, checksums |

`gene_counts_raw.tsv` format:

```tsv
gene_id	gene_name	SAMPLE_001	SAMPLE_002
ENSG00000000003.18	TSPAN6	12	9
ENSG00000000419.16	DPM1	301	277
```

The counts measure type must be:

```text
assigned_longread_gene_counts
```

It must not be named or interpreted as:

```text
estimated_counts_unscaled
```

## Long-read validation

Validation should check:

1. Input FASTQ exists and checksum matches.
2. Reference FASTA/GTF exists and checksum matches.
3. Counts table has `gene_id`, `gene_name`, and exactly the expected sample columns.
4. Counts are numeric, finite, non-negative values.
5. Gene identifiers exist in the governed GTF.
6. Alignment summary exists for each sample.
7. QC metrics exist for each sample.
8. Provenance includes method profile, reference profile, tool versions, command, parameters, and input manifest checksum.

Initial QC metrics:

| Metric | v1 status |
|---|---|
| total_reads | required |
| total_bases | required |
| read_n50 | warning if missing |
| mean_read_length | warning if missing |
| alignment_rate | required |
| primary_alignment_rate | warning if missing |
| gene_assignment_rate | required |
| mitochondrial_percent | warning if missing |
| rrna_percent | warning if missing |

Thresholds should be warning-oriented in v1. A run should fail only for missing required artifacts, invalid counts, failed traceability, or very poor core alignment/assignment metrics once project thresholds are explicitly approved.

## Relationship to current short-read MVP

The platform should be described as:

```text
RNA-seq governance platform
├── short-read Bulk RNA-seq MVP
│   ├── Poly(A)+
│   └── rRNA depletion
└── long-read RNA-seq MVP
    └── ONT gene-level counts v1
```

This avoids two mistakes:

1. Treating long-read RNA-seq as just another parameter of `nf-core/rnaseq`.
2. Creating a completely separate project that duplicates governance logic.

## Commands

Current repository verification commands:

```powershell
$env:PYTHONPATH='src'; python -m ruff check .
$env:PYTHONPATH='src'; python -m pytest -q
```

Preferred project commands when the Linux/uv environment is healthy:

```bash
uv run ruff check .
uv run pytest -q
uv run rnaseq-mvp --help
```

The long-read workflow command must be added only after the deterministic runner is implemented and tool versions are pinned.

## Project structure

Recommended structure inside the current repository:

```text
src/rnaseq_mvp/
  governance/              # shared contracts over time, if refactoring is approved
  longread.py              # long-read command and postprocess helpers
  validator.py             # shared count validation plus profile-specific routing
  prepare.py               # shared file/reference preparation, profile-specific samplesheets

definitions/
  methods/
    longread_rnaseq_minimap2_gene_counts_v1.yaml
  validation/
    longread_rnaseq_gene_counts_v1.yaml

configs/
  longread/
    minimap2_gene_counts_v1.yaml

docs/
  design/
  operations/
  examples/
```

Do not create a separate repository for the first long-read MVP unless the long-read runner grows large enough to justify independent release/versioning.

## Testing strategy

Add tests in this order:

1. Definition tests:
   - long-read method and validation profiles load
   - unsupported long-read metadata fails clearly

2. Preparation tests:
   - long-read samplesheet is generated
   - input manifest records checksum and sample identity

3. Runner tests:
   - long-read method does not build an nf-core/rnaseq command
   - long-read command includes pinned minimap2/counting parameters
   - unsupported platform/protocol fails before execution

4. Postprocessing tests:
   - raw tool outputs are normalized into `longread/gene_counts_raw.tsv`
   - provenance records measure type and method profile

5. Validation tests:
   - valid minimal long-read counts pass
   - missing alignment summary fails
   - missing optional QC metrics warn
   - unknown gene IDs fail

6. Integration smoke test:
   - tiny artificial FASTQ or prebuilt mini fixture
   - tiny reference FASTA/GTF
   - no full public dataset required in unit tests

## Boundaries

Always do:

- Keep long-read outputs separate from STAR/Salmon outputs.
- Preserve shared governance traceability.
- Record `analysis_profile_id`, `method_profile_id`, `validation_policy_id`, `reference_profile_id`, and `measure_type`.
- Use deterministic tools for alignment, counting, QC, and validation.
- Keep current Poly(A)+ and rRNA depletion short-read behavior working.

Ask first:

- Adding a new container system or workflow manager.
- Supporting PacBio in the first runnable implementation.
- Making high rRNA/mitochondrial percentages hard failures.
- Accepting BAM as a primary input instead of FASTQ.
- Adding isoform-level outputs as governed primary outputs.

Never do:

- Run long-read FASTQ through `STAR + Salmon + tximport`.
- Label long-read assigned counts as Salmon estimated counts.
- Infer platform/protocol from filename alone.
- Use LLM judgment as a substitute for QC metrics.
- Mix long-read and short-read counts in downstream analysis without profile and batch metadata.

## Success criteria

The long-read MVP is complete when:

- A long-read dataset definition can be loaded with explicit ONT metadata.
- The tool can prepare checksummed input and reference manifests.
- The tool can generate a long-read samplesheet.
- The runner can execute or dry-run a deterministic long-read command that is not nf-core/rnaseq.
- Postprocessing writes `longread/gene_counts_raw.tsv`.
- Validation produces `validation_report.json`, `qc_metrics.tsv`, and `validation_summary.tsv`.
- Existing short-read tests still pass.
- Documentation explains to users when to use short-read MVP versus long-read MVP.

## Open questions

1. Should v1 be ONT-only, or should PacBio Iso-Seq be included from the first runnable version?
2. Should v1 accept only FASTQ, or also accept pre-aligned BAM from trusted public repositories?
3. Which deterministic gene assignment tool should be pinned first: featureCounts long-read mode, htseq-count, or another explicitly verified tool?
4. Should the long-read runner be a Python wrapper around command-line tools, a Nextflow mini-pipeline, or a separate nf-core-compatible workflow later?
5. Should isoform-level outputs be stored as optional secondary assets in v1, or deferred entirely?

