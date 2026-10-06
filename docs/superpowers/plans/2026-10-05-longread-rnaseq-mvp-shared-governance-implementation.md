# Long-read RNA-seq MVP Shared Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first runnable long-read RNA-seq MVP path that shares the existing governance framework but does not use the short-read STAR/Salmon pipeline.

**Architecture:** Keep shared state, manifest, reference, validation, and provenance concepts in the current package. Add a long-read-specific samplesheet builder, command builder, and postprocessing/validation contract under a separate method family.

**Tech Stack:** Python, Pydantic, pandas, PyYAML, Typer, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-05-longread-rnaseq-mvp-shared-governance-design.md`

## Global Constraints

- Long-read FASTQ must not be routed to `nf-core/rnaseq`, STAR, Salmon, or tximport.
- Long-read counts must use `assigned_longread_gene_counts`, not `estimated_counts_unscaled`.
- The first runnable version targets human ONT FASTQ to gene-level counts.
- Existing short-read Poly(A)+ and rRNA depletion behavior must keep passing.
- All analysis/QC/validation decisions must remain deterministic.

## Review Focus

- A long-read method must produce a command distinct from `nextflow run nf-core/rnaseq`.
- The long-read samplesheet must use `sample,input_file,platform,protocol,strandedness,reference_profile_id`.
- Unsupported PacBio or unknown protocol must fail before execution in v1.
- Long-read postprocessing must publish `longread/gene_counts_raw.tsv` without renaming it to Salmon counts.
- Existing `T2A`/`T2B` tests must remain green.

---

### Task 1: Add long-read dataset metadata model support

**Files:**
- Modify: `src/rnaseq_mvp/models.py`
- Test: `tests/unit/test_definitions.py`

**Interfaces:**
- Produces: controlled support for `sequencing_platform="ONT"` and `library_selection` values used by long-read RNA-seq.
- Consumes: existing `DatasetDefinition.profile_id == "human_longread_rnaseq_v1"` and `read_layout == "long-read"`.

- [ ] Write failing tests for valid ONT cDNA/direct RNA long-read dataset definitions and rejected non-ONT v1 datasets.
- [ ] Run `python -m pytest tests/unit/test_definitions.py -q` with `PYTHONPATH=src` and verify failure.
- [ ] Implement profile-specific validation in `DatasetDefinition`.
- [ ] Re-run the same tests and verify pass.

### Task 2: Add long-read samplesheet generation

**Files:**
- Modify: `src/rnaseq_mvp/prepare.py`
- Test: `tests/integration/test_prepare.py`

**Interfaces:**
- Produces: `longread_samplesheet.csv` for long-read method families.
- Consumes: shared checksum download and `input_manifest.tsv` generation.

- [ ] Write failing test that prepares a long-read dataset and expects `longread_samplesheet.csv` with long-read columns.
- [ ] Run the targeted test and verify failure.
- [ ] Implement long-read samplesheet writer while keeping existing short-read `samplesheet.csv`.
- [ ] Re-run prepare integration tests.

### Task 3: Add long-read command builder

**Files:**
- Modify: `src/rnaseq_mvp/runner.py`
- Test: `tests/unit/test_runner.py`

**Interfaces:**
- Produces: `build_pipeline_command(..., method=MethodDefinition)` dispatcher and `build_longread_command`.
- Consumes: existing `build_nextflow_command` for short-read methods.

- [ ] Write failing tests proving long-read command is not `nf-core/rnaseq` and contains `rnaseq-mvp-longread`.
- [ ] Run runner tests and verify failure.
- [ ] Implement dispatcher and use it in `run_stage`.
- [ ] Re-run runner tests.

### Task 4: Add long-read postprocessing helper

**Files:**
- Create: `src/rnaseq_mvp/longread.py`
- Test: `tests/unit/test_longread.py`

**Interfaces:**
- Produces: `write_longread_postprocess_outputs(...)` for normalizing minimal long-read output fixtures.
- Consumes: shared TSV writing and checksum concepts.

- [ ] Write failing tests for creating `longread/gene_counts_raw.tsv`, `alignment_summary.tsv`, `longread_qc_metrics.tsv`, and `provenance.json`.
- [ ] Run targeted tests and verify failure.
- [ ] Implement minimal deterministic helper.
- [ ] Re-run targeted tests.

### Task 5: Final verification and documentation update

**Files:**
- Modify: `docs/design/2026-10-05-rnaseq-profile-expansion-postprocessing.md`
- Test: full suite

**Interfaces:**
- Consumes: all prior tasks.
- Produces: updated documentation that distinguishes “structure exists” from “runnable long-read stub exists”.

- [ ] Update documentation with the new long-read MVP entry points.
- [ ] Run `python -m ruff check .` with `PYTHONPATH=src`.
- [ ] Run `python -m pytest -q` with `PYTHONPATH=src`.

