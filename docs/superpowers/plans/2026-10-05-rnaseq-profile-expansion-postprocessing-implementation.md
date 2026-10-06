# RNA-seq Profile Expansion Postprocessing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the MVP code structure so it can represent and route `human_illumina_rrna_depletion_bulk_v1` and `human_longread_rnaseq_v1` without breaking the frozen Poly(A)+ STAR/Salmon path.

**Architecture:** Add explicit profile and method typing to the definition layer, then make preparation and validation branch on method semantics instead of assuming one paired-end STAR/Salmon shape. Keep all analysis deterministic; long-read support in this pass is a governed postprocessing contract and validation path, not a full new upstream aligner runner.

**Tech Stack:** Python 3.11+, Pydantic, Typer, pandas, PyYAML, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-05-rnaseq-profile-expansion-postprocessing-design.md`

## Global Constraints

- Preserve the existing Poly(A)+ `T2A` and `T2B` behavior.
- The current formal human reference remains GRCh38.p14 + GENCODE Release 50 unless a future profile explicitly changes it.
- LLMs may orchestrate and explain, but deterministic tools perform analysis, QC, validation, and file generation.
- Do not label long-read assigned gene counts as Salmon estimated counts.
- Reject unknown metadata rather than silently inferring library selection or read layout.
- First long-read version targets governed gene-level counts only, not isoform discovery, fusion discovery, or RNA modification analysis.

## Review Focus

- Existing `ENCSR000AEM` definitions must still load and freeze as before.
- Single-end short-read samples must emit a valid nf-core samplesheet with empty `fastq_2`, not fail as missing R2.
- rRNA depletion datasets must use separate validation policy identifiers so Poly(A)+ QC assumptions are not silently reused.
- Long-read methods must not be sent through the STAR/Salmon artifact validator.
- Unknown method families or library selections must fail loudly during definition loading or validation.

---

### Task 1: Add profile-aware definition models

**Files:**
- Modify: `src/rnaseq_mvp/models.py`
- Test: `tests/unit/test_definitions.py`

**Interfaces:**
- Produces: `DatasetDefinition.profile_id: str`, `DatasetDefinition.read_layout`, `DatasetDefinition.library_selection`, `SampleDefinition.read_files_by_role()`, `MethodDefinition.method_family`, and `MethodDefinition.counts_measure_type`.
- Consumes: Existing YAML definitions remain valid by deriving a default `profile_id`.

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_dataset_definition_accepts_rrna_depletion_single_end() -> None:
    ...
    assert dataset.profile_id == "human_illumina_rrna_depletion_bulk_v1"
    assert dataset.samples[0].read_files_by_role()["R1"].filename == "S1_R1.fastq.gz"

def test_method_definition_accepts_longread_gene_counts() -> None:
    ...
    assert method.method_family == "longread_gene_counts"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_definitions.py -q`

Expected: FAIL because the current literals reject rRNA depletion, single-end, and long-read method metadata.

- [ ] **Step 3: Implement minimal model changes**

Add controlled literals for source databases, profile IDs, read layouts, library selections, strandedness values, file roles, method families, pipeline names, aligners, quantifiers, aggregations, and counts measure types. Keep default `profile_id="human_illumina_polya_bulk_v1"` for existing datasets.

- [ ] **Step 4: Run task tests**

Run: `uv run pytest tests/unit/test_definitions.py -q`

Expected: PASS.

### Task 2: Make preparation support single-end short-read profiles

**Files:**
- Modify: `src/rnaseq_mvp/prepare.py`
- Test: `tests/integration/test_prepare.py`

**Interfaces:**
- Consumes: `SampleDefinition.read_files_by_role()` and `DatasetDefinition.read_layout`.
- Produces: nf-core-compatible samplesheets where paired-end samples have `fastq_2` and single-end samples have an empty `fastq_2`.

- [ ] **Step 1: Write failing integration test**

Add a test that builds a single-end `human_illumina_rrna_depletion_bulk_v1` registry and asserts generated `samplesheet.csv` contains:

```csv
sample,fastq_1,fastq_2,strandedness,seq_platform,seq_center
TEST_SAMPLE,/.../TEST_R1.fastq.gz,,auto,ILLUMINA,TEST_CENTER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_prepare.py::test_prepare_writes_single_end_rrna_depletion_samplesheet -q`

Expected: FAIL because preparation currently requires exactly R1 and R2.

- [ ] **Step 3: Implement minimal preparation routing**

Replace the hard-coded paired-end role check with `read_files_by_role()`. For paired-end require R1/R2; for single-end require only R1. Emit `seq_platform` from the dataset and `seq_center` from a new optional dataset field with a conservative default.

- [ ] **Step 4: Run task tests**

Run: `uv run pytest tests/integration/test_prepare.py -q`

Expected: PASS.

### Task 3: Add profile-aware validation artifact routing

**Files:**
- Modify: `src/rnaseq_mvp/validator.py`
- Test: `tests/unit/test_validator.py`

**Interfaces:**
- Produces: `required_artifacts_for_method(results_dir, method)` and `counts_path_for_method(results_dir, method)`.
- Consumes: `MethodDefinition.method_family` and `MethodDefinition.counts_measure_type`.

- [ ] **Step 1: Write failing unit tests**

Add tests proving:

```python
def test_shortread_star_salmon_artifact_contract_is_unchanged(tmp_path): ...
def test_longread_gene_counts_artifact_contract_uses_longread_postprocess(tmp_path): ...
def test_unknown_method_family_rejected_by_validator(tmp_path): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validator.py -q`

Expected: FAIL because validator currently hard-codes STAR/Salmon paths.

- [ ] **Step 3: Implement minimal routing helpers**

For `shortread_star_salmon`, keep existing STAR/Salmon required artifacts unchanged. For `longread_gene_counts`, require `longread/gene_counts_raw.tsv`, `longread/alignment_summary.tsv`, `longread/longread_qc_metrics.tsv`, and `longread/provenance.json`.

- [ ] **Step 4: Run task tests**

Run: `uv run pytest tests/unit/test_validator.py -q`

Expected: PASS.

### Task 4: Add new definition YAMLs and schemas

**Files:**
- Create: `definitions/methods/bulk_rnaseq_star_salmon_rrna_depletion_v1.yaml`
- Create: `definitions/methods/longread_rnaseq_minimap2_gene_counts_v1.yaml`
- Create: `definitions/validation/bulk_rnaseq_rrna_depletion_v1.yaml`
- Create: `definitions/validation/longread_rnaseq_gene_counts_v1.yaml`
- Modify: `schemas/*.schema.json`
- Test: `tests/unit/test_frozen_definitions.py`

**Interfaces:**
- Consumes: model changes from Task 1.
- Produces: loadable named method and validation profiles for future stages.

- [ ] **Step 1: Write failing frozen-definition tests**

Add tests asserting the four new profile definitions load and have the expected IDs and `counts_measure_type` values.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_frozen_definitions.py -q`

Expected: FAIL because the new YAMLs do not exist.

- [ ] **Step 3: Add YAML definitions and regenerate schemas**

Add the four YAML files and run: `uv run python scripts/export_schemas.py`

- [ ] **Step 4: Run task tests**

Run: `uv run pytest tests/unit/test_frozen_definitions.py tests/unit/test_schema_export.py -q`

Expected: PASS.

### Task 5: Document the new postprocessing structure

**Files:**
- Create: `docs/design/2026-10-05-rnaseq-profile-expansion-postprocessing.md`
- Test: `uv run ruff check .` and `uv run pytest -q`

**Interfaces:**
- Consumes: implemented model fields and definition IDs.
- Produces: Chinese-facing technical explanation for why rRNA depletion and long-read outputs are separated.

- [ ] **Step 1: Write documentation**

Document the supported profiles, input expectations, processing/postprocessing paths, outputs, and current boundaries.

- [ ] **Step 2: Run full verification**

Run:

```powershell
uv run ruff check .
uv run pytest -q
```

Expected: PASS.

