# Public Bulk RNA-seq Catalog and Analysis Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned public Bulk RNA-seq catalog that imports curator-maintained Excel/CSV data, archives verified FASTQ, runs the frozen governance workflow once per analysis fingerprint, and exposes immutable reusable analysis assets through tenant-scoped project references.

**Architecture:** Add an isolated `rnaseq_mvp.catalog` package around the existing deterministic RNA-seq engine. SQLite stores catalog, audit, raw-asset, job, published-asset, and project-reference records; the filesystem stores staged imports, content-addressed FASTQ, and immutable release packages. A catalog pipeline adapter materializes verified public assets into the existing prepare/run/validate/review/package lifecycle without allowing users or an LLM to alter the frozen scientific method.

**Tech Stack:** Python 3.10–3.12, Typer, Pydantic 2, pandas 2, openpyxl 3.1, stdlib `sqlite3`, HTTPX, pytest, pytest-httpx, Ruff, Nextflow 25.10.4, nf-core/rnaseq 3.26.0, Docker.

**Spec:** `docs/superpowers/specs/2026-09-06-public-rnaseq-catalog-analysis-assets-design.md`

## Global Constraints

- Supported data scope is `Homo sapiens`, Illumina short-read conventional Bulk RNA-seq, Poly(A)+, single-end or paired-end.
- Standard analysis is STAR + Salmon + tximport with GRCh38.p14 and GENCODE Release 50.
- The baseline output is unscaled Salmon/tximport gene estimated counts; scaled counts, length-scaled counts, TPM, gene lengths, SummarizedExperiment RDS, QC, DQ, and provenance remain distinct measure types or artifacts.
- Nextflow is pinned to `25.10.4`; nf-core/rnaseq is pinned to `3.26.0`.
- v0.1 permits one catalog administrator to publish after deterministic validation; every publish action and evidence change is audited.
- Only `PUBLISHED` analysis assets with a verified immutable package may be reused.
- Archived FASTQ and standard release packages are retained; Nextflow work directories, container caches, transient files, and BAM are not permanent assets by default.
- Public subject identifiers never link to local patient `person_link_id` values.
- Excel/CSV is an ingestion format, not the query database.
- The LLM or future WeChat agent may call structured services but may not publish catalog entries, change scientific parameters, bypass validation, or invent accessions.
- Preserve existing T2A/T2B behavior and tests while adding catalog execution paths.
- Do not add FASTQ, BAM, credentials, patient data, or runtime archives to Git.

---

## File Map

New catalog code lives under `src/rnaseq_mvp/catalog/`:

- `models.py`: strict row, status, query, fingerprint, asset, and project-reference models.
- `serialization.py`: canonical JSON bytes shared by audit snapshots and fingerprints.
- `schema.sql`: SQLite schema, indexes, uniqueness constraints, and foreign keys.
- `database.py`: transaction boundary, migration bootstrap, and repository primitives.
- `workbook.py`: four-sheet Excel/four-file CSV parsing and canonical cell normalization.
- `validation.py`: relational, accession, layout, eligibility, and evidence validation.
- `imports.py`: staged import, diff, administrator publish, release snapshot, and audit events.
- `search.py`: structured catalog filtering and result cards.
- `raw_assets.py`: resumable acquisition, checksum verification, quarantine, content-addressed archive, and source-change handling.
- `fingerprints.py`: canonical JSON and data/method/analysis SHA-256 computation.
- `jobs.py`: unique analysis-job claims, subscribers, terminal state, and retry-safe transitions.
- `pipeline_adapter.py`: bridge from verified catalog records to the frozen RNA-seq engine.
- `assets.py`: immutable package registration, integrity checks, publish/withdraw, and project references.
- `service.py`: stable application-facing methods for future web and WeChat clients.
- `cli.py`: Typer subcommands for catalog import, publication, search, acquisition, analysis, and project references.

Supporting files:

- `templates/public_catalog_v0.1.xlsx`: generated curator workbook.
- `scripts/build_catalog_template.py`: deterministic workbook generator.
- `schemas/public_catalog_*.schema.json`: exported Pydantic contracts.
- `tests/fixtures/catalog/`: small four-table fixtures without real sequencing data.
- `tests/unit/catalog/`: focused domain and repository tests.
- `tests/integration/catalog/`: workbook, download, job, pipeline-adapter, and end-to-end tests.
- `docs/operations/public-catalog.md`: curator/operator runbook.

Existing files changed only at integration seams:

- `pyproject.toml`: add the Excel reader dependency.
- `src/rnaseq_mvp/cli.py`: register the catalog Typer sub-application.
- `src/rnaseq_mvp/models.py`: generalize stage identifiers and single/paired layout without weakening frozen-definition tests.
- `src/rnaseq_mvp/paths.py`: add catalog, archive, and asset paths.
- `src/rnaseq_mvp/prepare.py`: expose a preparation primitive for already-verified local FASTQ.
- `src/rnaseq_mvp/packager.py`: expose package verification metadata required by asset registration.
- `src/rnaseq_mvp/constants.py`: add catalog-specific exit codes without changing existing values.
- `README.md`: link the public-catalog operator guide.

---

### Task 1: Catalog domain models and deterministic workbook template

**Files:**
- Create: `src/rnaseq_mvp/catalog/__init__.py`
- Create: `src/rnaseq_mvp/catalog/models.py`
- Create: `scripts/build_catalog_template.py`
- Create: `templates/public_catalog_v0.1.xlsx`
- Create: `tests/unit/catalog/test_models.py`
- Create: `tests/unit/catalog/test_template.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Pydantic `BaseModel`, existing Python version range, the four-sheet contract in the approved spec.
- Produces: `StudyRow`, `SampleRow`, `RunFileRow`, `EligibilityReviewRow`, `CatalogWorkbook`, `ImportStatus`, `AssetStatus`, and `SearchQuery`.

- [ ] **Step 1: Add the Excel dependency and empty package**

Add `openpyxl>=3.1,<4` to project dependencies, create `catalog/__init__.py`, run `uv lock`, and verify the lockfile records openpyxl.

Run: `uv lock && uv sync --extra dev`

Expected: dependency resolution succeeds under Python 3.10–3.12.

- [ ] **Step 2: Write failing strict-model tests**

```python
def test_paired_run_requires_one_r1_and_one_r2() -> None:
    rows = [_run_file("R1"), _run_file("R1")]
    with pytest.raises(ValueError, match="exactly one R1 and one R2"):
        CatalogWorkbook(
            studies=[_study()], samples=[_sample()], runs_files=rows,
            eligibility_reviews=[_eligibility()],
        )


def test_missing_public_metadata_is_explicit() -> None:
    row = _sample(age_raw="", age_value=None, age_unit="")
    with pytest.raises(ValueError, match="NOT_REPORTED"):
        SampleRow.model_validate(row)
```

Run: `uv run pytest tests/unit/catalog/test_models.py -v`

Expected: FAIL because `rnaseq_mvp.catalog.models` does not exist.

- [ ] **Step 3: Implement strict models and enums**

Use `ConfigDict(extra="forbid")`, timezone-aware datetimes, and these exact public types:

```python
MissingValue = Literal["NOT_REPORTED", "NOT_APPLICABLE"]
ReviewValue = Literal["PASS", "FAIL", "NOT_REPORTED", "NOT_APPLICABLE"]
FileRole = Literal["R1", "R2"]
LibraryLayout = Literal["single-end", "paired-end"]

class ImportStatus(str, Enum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"

class AssetStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    CURATED = "CURATED"
    ELIGIBLE = "ELIGIBLE"
    FASTQ_VERIFIED = "FASTQ_VERIFIED"
    PROCESSING = "PROCESSING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
```

Implement workbook-level checks for unique source/accession keys and R1/R2 cardinality. Keep source raw values and normalized values as separate fields.
Represent `expected_md5` as a validated lowercase 32-character digest or the literal `NOT_REPORTED`; convert `NOT_REPORTED` to SQL `NULL` only at the persistence boundary.

- [ ] **Step 4: Generate the four-sheet workbook deterministically**

`scripts/build_catalog_template.py` must write sheets in this order: `studies`, `samples`, `runs_files`, `eligibility_review`; freeze the first row, enable filters, apply data validation to controlled-value columns, and add a second-row Chinese explanation in a separate `instructions` sheet rather than mixing prose with import rows.

Run: `uv run python scripts/build_catalog_template.py --output templates/public_catalog_v0.1.xlsx`

Expected: the workbook exists and can be loaded by openpyxl.

- [ ] **Step 5: Verify workbook geometry and model headers**

```python
def test_template_headers_match_models() -> None:
    workbook = load_workbook(TEMPLATE, read_only=True)
    assert workbook.sheetnames == [
        "instructions", "studies", "samples", "runs_files", "eligibility_review"
    ]
    assert _headers(workbook["studies"]) == list(StudyRow.model_fields)
```

Run: `uv run pytest tests/unit/catalog/test_models.py tests/unit/catalog/test_template.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the domain contract**

```bash
git add pyproject.toml uv.lock src/rnaseq_mvp/catalog scripts/build_catalog_template.py templates/public_catalog_v0.1.xlsx tests/unit/catalog
git commit -m "feat: define public catalog workbook contract"
```

---

### Task 2: SQLite schema, repository, and audit boundary

**Files:**
- Create: `src/rnaseq_mvp/catalog/schema.sql`
- Create: `src/rnaseq_mvp/catalog/database.py`
- Create: `src/rnaseq_mvp/catalog/serialization.py`
- Create: `tests/unit/catalog/test_database.py`
- Create: `tests/unit/catalog/test_serialization.py`
- Modify: `src/rnaseq_mvp/paths.py`
- Modify: `tests/unit/test_paths.py`

**Interfaces:**
- Consumes: catalog models from Task 1 and `WorkspacePaths`.
- Produces: `canonical_json_bytes(value) -> bytes`, `CatalogRepository.open(path)`, `CatalogRepository.transaction()`, `CatalogRepository.record_audit(event_id, object_type, object_id, actor_id, action, occurred_at, reason, payload)`, and persistent tables used by all remaining tasks.

- [ ] **Step 1: Extend workspace paths with catalog-owned directories**

Add immutable dataclass fields and map them under the workspace root:

```python
catalog = resolved / "catalog"
catalog_staging = catalog / "staging"
catalog_snapshots = catalog / "snapshots"
raw_archive = resolved / "archive" / "fastq" / "sha256"
analysis_assets = resolved / "assets" / "analysis"
```

Update `test_paths.py` to assert exact resolved paths.

- [ ] **Step 2: Write failing canonical-serialization, migration, and foreign-key tests**

```python
def test_open_creates_schema_and_enforces_foreign_keys(tmp_path: Path) -> None:
    repo = CatalogRepository.open(tmp_path / "catalog.sqlite3")
    assert repo.schema_version() == 1
    with pytest.raises(sqlite3.IntegrityError):
        repo.connection.execute(
            "INSERT INTO public_sample(public_sample_version_id, public_sample_id, public_study_version_id, source_database, sample_accession, payload_json) VALUES(?,?,?,?,?,?)",
            ("sv1", "s1", "missing", "SRA", "SRS1", "{}"),
        )


def test_canonical_json_is_stable_across_mapping_order() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
```

Run: `uv run pytest tests/unit/catalog/test_database.py tests/unit/catalog/test_serialization.py -v`

Expected: FAIL because the repository and schema do not exist.

- [ ] **Step 3: Create schema version 1**

`schema.sql` must enable foreign keys and create normalized tables:

```sql
PRAGMA foreign_keys = ON;
CREATE TABLE schema_meta(version INTEGER NOT NULL);
CREATE TABLE catalog_import(
  import_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('UPLOADED','VALIDATING','VALIDATION_FAILED','READY_FOR_REVIEW','PUBLISHED','REJECTED')),
  source_path TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL,
  validation_json TEXT NOT NULL
);
CREATE TABLE catalog_release(
  catalog_release_id TEXT PRIMARY KEY, import_id TEXT NOT NULL UNIQUE,
  release_year INTEGER NOT NULL, release_sequence INTEGER NOT NULL,
  released_by TEXT NOT NULL, release_reason TEXT NOT NULL, released_at TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL, FOREIGN KEY(import_id) REFERENCES catalog_import(import_id),
  UNIQUE(release_year, release_sequence)
);
CREATE TABLE public_study(
  public_study_version_id TEXT PRIMARY KEY, public_study_id TEXT NOT NULL,
  catalog_release_id TEXT NOT NULL,
  source_database TEXT NOT NULL, study_accession TEXT NOT NULL, payload_json TEXT NOT NULL,
  FOREIGN KEY(catalog_release_id) REFERENCES catalog_release(catalog_release_id),
  UNIQUE(public_study_id, catalog_release_id),
  UNIQUE(source_database, study_accession, catalog_release_id)
);
CREATE TABLE public_sample(
  public_sample_version_id TEXT PRIMARY KEY, public_sample_id TEXT NOT NULL,
  public_study_version_id TEXT NOT NULL,
  source_database TEXT NOT NULL, sample_accession TEXT NOT NULL, payload_json TEXT NOT NULL,
  FOREIGN KEY(public_study_version_id) REFERENCES public_study(public_study_version_id),
  UNIQUE(public_sample_id, public_study_version_id)
);
CREATE TABLE public_assay(
  assay_version_id TEXT PRIMARY KEY, assay_id TEXT NOT NULL,
  public_sample_version_id TEXT NOT NULL,
  experiment_accession TEXT NOT NULL, payload_json TEXT NOT NULL,
  FOREIGN KEY(public_sample_version_id) REFERENCES public_sample(public_sample_version_id),
  UNIQUE(assay_id, public_sample_version_id)
);
CREATE TABLE sequencing_run(
  sequencing_run_version_id TEXT PRIMARY KEY, sequencing_run_id TEXT NOT NULL,
  assay_version_id TEXT NOT NULL,
  run_accession TEXT NOT NULL, library_layout TEXT NOT NULL, payload_json TEXT NOT NULL,
  FOREIGN KEY(assay_version_id) REFERENCES public_assay(assay_version_id),
  UNIQUE(sequencing_run_id, assay_version_id)
);
CREATE TABLE source_file(
  source_file_version_id TEXT PRIMARY KEY, source_file_id TEXT NOT NULL,
  sequencing_run_version_id TEXT NOT NULL,
  catalog_release_id TEXT NOT NULL, source_database TEXT NOT NULL,
  file_accession TEXT NOT NULL, file_role TEXT NOT NULL, download_url TEXT NOT NULL,
  expected_bytes INTEGER NOT NULL, expected_md5 TEXT,
  state TEXT NOT NULL CHECK(state IN ('REGISTERED','DOWNLOADING','DOWNLOADED','VERIFIED','ARCHIVED','DOWNLOAD_FAILED','QUARANTINED')),
  FOREIGN KEY(sequencing_run_version_id) REFERENCES sequencing_run(sequencing_run_version_id),
  FOREIGN KEY(catalog_release_id) REFERENCES catalog_release(catalog_release_id),
  UNIQUE(source_file_id, catalog_release_id),
  UNIQUE(source_database, file_accession, catalog_release_id)
);
CREATE TABLE eligibility_review(
  eligibility_review_id TEXT PRIMARY KEY, public_study_version_id TEXT NOT NULL,
  status TEXT NOT NULL, payload_json TEXT NOT NULL,
  FOREIGN KEY(public_study_version_id) REFERENCES public_study(public_study_version_id)
);
CREATE TABLE raw_asset(
  raw_asset_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, bytes INTEGER NOT NULL,
  archive_path TEXT NOT NULL UNIQUE, gzip_status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE raw_asset_source(
  raw_asset_id TEXT NOT NULL, source_file_version_id TEXT NOT NULL, observed_md5 TEXT,
  verified_at TEXT NOT NULL, PRIMARY KEY(raw_asset_id, source_file_version_id),
  FOREIGN KEY(raw_asset_id) REFERENCES raw_asset(raw_asset_id),
  FOREIGN KEY(source_file_version_id) REFERENCES source_file(source_file_version_id)
);
CREATE TABLE analysis_job(
  job_id TEXT PRIMARY KEY, analysis_fingerprint TEXT NOT NULL, active_fingerprint TEXT,
  status TEXT NOT NULL CHECK(status IN ('QUEUED','PREPARING','PROCESSING','VALIDATING','AWAITING_REVIEW','PUBLISHED','FAILED','WITHDRAWN')),
  stage_id TEXT, run_id TEXT, failure_reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_active_analysis_job
ON analysis_job(active_fingerprint) WHERE active_fingerprint IS NOT NULL;
CREATE TABLE analysis_job_subscriber(
  job_id TEXT NOT NULL, requester_id TEXT NOT NULL, subscribed_at TEXT NOT NULL,
  PRIMARY KEY(job_id, requester_id), FOREIGN KEY(job_id) REFERENCES analysis_job(job_id)
);
CREATE TABLE analysis_asset(
  analysis_asset_id TEXT PRIMARY KEY, analysis_fingerprint TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK(status IN ('PUBLISHED','SUPERSEDED','WITHDRAWN')),
  package_path TEXT NOT NULL UNIQUE, package_sha256 TEXT NOT NULL,
  published_by TEXT NOT NULL, published_at TEXT NOT NULL, withdrawal_reason TEXT
);
CREATE TABLE analysis_asset_input(
  analysis_asset_id TEXT NOT NULL, raw_asset_id TEXT NOT NULL,
  PRIMARY KEY(analysis_asset_id, raw_asset_id),
  FOREIGN KEY(analysis_asset_id) REFERENCES analysis_asset(analysis_asset_id),
  FOREIGN KEY(raw_asset_id) REFERENCES raw_asset(raw_asset_id)
);
CREATE TABLE project_asset_ref(
  project_asset_ref_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
  analysis_asset_id TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  FOREIGN KEY(analysis_asset_id) REFERENCES analysis_asset(analysis_asset_id),
  UNIQUE(tenant_id, project_id, analysis_asset_id)
);
CREATE TABLE data_discovery_request(
  discovery_request_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
  requester_id TEXT NOT NULL, query_json TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, resolved_at TEXT, resolution_note TEXT
);
CREATE TABLE audit_event(
  event_id TEXT PRIMARY KEY, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
  actor_id TEXT NOT NULL, action TEXT NOT NULL, occurred_at TEXT NOT NULL,
  reason TEXT NOT NULL, payload_json TEXT NOT NULL
);
```

Use UTC ISO-8601 strings, JSON text for immutable payload snapshots, and explicit status `CHECK` constraints. Do not store direct patient identifiers.

- [ ] **Step 4: Implement transaction and audit primitives**

Implement `canonical_json_bytes(value: JSONValue) -> bytes` in `serialization.py` using sorted keys, UTF-8, separators `(',', ':')`, `ensure_ascii=False`, and rejection of NaN/Infinity. Implement `CatalogRepository.open(path: Path) -> CatalogRepository` to create the parent directory, connect, enable foreign keys, apply schema version 1 once, and return the repository. Implement `CatalogRepository.transaction() -> Iterator[sqlite3.Connection]` as a context manager around `BEGIN IMMEDIATE`. Implement `CatalogRepository.record_audit(event_id: str, object_type: str, object_id: str, actor_id: str, action: str, occurred_at: datetime, reason: str, payload: Mapping[str, Any]) -> None` with keyword-only arguments and canonical payload serialization.

Transactions use `BEGIN IMMEDIATE`, commit on success, and rollback on any exception.

- [ ] **Step 5: Test rollback, uniqueness, and audit persistence**

Run: `uv run pytest tests/unit/catalog/test_database.py tests/unit/catalog/test_serialization.py tests/unit/test_paths.py -v`

Expected: PASS, including a test proving a failed multi-table insert leaves zero partial rows.

- [ ] **Step 6: Commit persistence foundations**

```bash
git add src/rnaseq_mvp/catalog/schema.sql src/rnaseq_mvp/catalog/database.py src/rnaseq_mvp/catalog/serialization.py src/rnaseq_mvp/paths.py tests/unit/catalog/test_database.py tests/unit/catalog/test_serialization.py tests/unit/test_paths.py
git commit -m "feat: add versioned catalog persistence"
```

---

### Task 3: Workbook parser and deterministic validation report

**Files:**
- Create: `src/rnaseq_mvp/catalog/workbook.py`
- Create: `src/rnaseq_mvp/catalog/validation.py`
- Create: `tests/fixtures/catalog/valid/`
- Create: `tests/fixtures/catalog/valid.xlsx`
- Create: `tests/fixtures/catalog/missing_r2/`
- Create: `tests/unit/catalog/test_workbook.py`
- Create: `tests/unit/catalog/test_validation.py`
- Create: `tests/integration/catalog/test_url_probe.py`

**Interfaces:**
- Consumes: Task 1 row models.
- Produces: `load_catalog_bundle(path: Path) -> CatalogWorkbook`, `UrlProbe`, `HttpxUrlProbe`, `validate_catalog(workbook: CatalogWorkbook, url_probe: UrlProbe) -> CatalogValidationReport`, and row-addressed `CatalogIssue` objects.

- [ ] **Step 1: Write failing Excel and CSV bundle tests**

```python
def test_excel_and_four_csv_bundle_parse_identically() -> None:
    excel = load_catalog_bundle(FIXTURES / "valid.xlsx")
    csvs = load_catalog_bundle(FIXTURES / "valid")
    assert excel.model_dump(mode="json") == csvs.model_dump(mode="json")
```

Run: `uv run pytest tests/unit/catalog/test_workbook.py -v`

Expected: FAIL because the loader does not exist.

- [ ] **Step 2: Implement canonical parsing**

Normalize headers by exact match only; trim leading/trailing whitespace from textual cells; convert spreadsheet date cells to UTC-aware values; preserve evidence text verbatim apart from line-ending normalization. Reject unknown sheets, missing sheets, duplicate headers, formula cells, and extra fields.

CSV bundle names are exactly `studies.csv`, `samples.csv`, `runs_files.csv`, and `eligibility_review.csv`, encoded as UTF-8 with BOM accepted.

- [ ] **Step 3: Write failing relational and eligibility tests**

```python
def test_validation_reports_sheet_row_field() -> None:
    report = validate_catalog(_paired_workbook_without_r2(), FakeUrlProbe.reachable())
    issue = report.errors[0]
    assert (issue.sheet, issue.row, issue.field, issue.code) == (
        "runs_files", 2, "file_role", "PAIRED_R2_MISSING"
    )


def test_polya_requires_human_confirmed_pass() -> None:
    report = validate_catalog(
        _workbook(polya_status="NOT_REPORTED"), FakeUrlProbe.reachable()
    )
    assert "ELIGIBILITY_NOT_CONFIRMED" in {issue.code for issue in report.errors}
```

- [ ] **Step 4: Implement cross-table validation**

Check foreign keys, accession namespace patterns, uniqueness, sample counts, R1/R2 cardinality, HTTPS URLs, positive byte sizes, lowercase MD5 where supplied, and all eligibility gates. `UrlProbe.check(url) -> UrlProbeResult` follows redirects, rejects a final non-HTTPS URL, and records final URL plus HTTP status; unit tests use a fake probe and integration tests use `httpx.MockTransport`. Represent every error as:

```python
class CatalogIssue(BaseModel):
    severity: Literal["ERROR", "WARNING"]
    code: str
    sheet: str
    row: int
    field: str
    message: str
```

The report is `PASS`, `PASS_WITH_WARNINGS`, or `FAIL`; only `PASS` and `PASS_WITH_WARNINGS` may proceed to administrator review.

- [ ] **Step 5: Verify redirect, unavailable URL, and validation behavior**

`test_url_probe.py` uses `httpx.MockTransport` to prove a reachable HTTPS redirect passes, an HTTPS-to-HTTP redirect fails, and 404/500 responses produce row-addressed `URL_UNREACHABLE` errors.

Run: `uv run pytest tests/unit/catalog/test_workbook.py tests/unit/catalog/test_validation.py tests/integration/catalog/test_url_probe.py -v`

Expected: PASS.

- [ ] **Step 6: Commit import parsing and validation**

```bash
git add src/rnaseq_mvp/catalog/workbook.py src/rnaseq_mvp/catalog/validation.py tests/fixtures/catalog tests/unit/catalog/test_workbook.py tests/unit/catalog/test_validation.py tests/integration/catalog/test_url_probe.py
git commit -m "feat: validate curated catalog workbooks"
```

---

### Task 4: Staged imports, release diff, administrator publication, and CLI

**Files:**
- Create: `src/rnaseq_mvp/catalog/imports.py`
- Create: `src/rnaseq_mvp/catalog/cli.py`
- Create: `tests/integration/catalog/test_import_publish.py`
- Create: `tests/unit/catalog/test_imports.py`
- Modify: `src/rnaseq_mvp/cli.py`
- Modify: `src/rnaseq_mvp/constants.py`

**Interfaces:**
- Consumes: repository, parser, and validation report from Tasks 2–3.
- Produces: `stage_import(source, workspace, actor_id, now, url_probe) -> StagedImport`, `diff_import(import_id, workspace) -> CatalogDiff`, `publish_import(import_id, workspace, actor_id, reason, now) -> CatalogRelease`, and CLI commands `catalog import`, `catalog diff`, `catalog publish`, `catalog reject`.

- [ ] **Step 1: Write a failing atomic-publication integration test**

```python
def test_publish_creates_immutable_release_and_audit(tmp_path: Path) -> None:
    staged = stage_import(
        VALID_XLSX, tmp_path, actor_id="curator-1", now=NOW,
        url_probe=FakeUrlProbe.reachable(),
    )
    release = publish_import(
        staged.import_id, tmp_path, actor_id="admin-1",
        reason="initial curated release", now=NOW,
    )
    assert release.catalog_release_id == "PUBLIC_CATALOG_2026_001"
    assert _count(tmp_path, "public_study") == 1
    assert _audit_actions(tmp_path) == ["IMPORT_STAGED", "CATALOG_PUBLISHED"]
```

Run: `uv run pytest tests/integration/catalog/test_import_publish.py -v`

Expected: FAIL because import services do not exist.

- [ ] **Step 2: Implement staging and immutable snapshots**

`stage_import` copies the submitted bundle to `catalog/staging/<import_id>/`, records SHA-256, parses and validates it with the injected URL probe, writes `validation_report.json`, and stores the canonical workbook snapshot as JSON. It never changes formal catalog tables. The CLI constructs `HttpxUrlProbe`; tests inject a deterministic fake.

- [ ] **Step 3: Implement release diff and publish transaction**

`CatalogDiff` contains exact `added`, `changed`, and `removed` keys per entity. `publish_import` requires `READY_FOR_REVIEW`, non-empty actor and reason, then creates the next yearly release ID, inserts a complete snapshot in one transaction, records the audit event, and writes `catalog/snapshots/<release_id>/catalog.json` plus `checksums.sha256`.

Reject attempts to republish the same import or mutate a published release.

- [ ] **Step 4: Add Typer sub-application**

Register `catalog_app` under the existing root app:

```python
from rnaseq_mvp.catalog.cli import catalog_app
app.add_typer(catalog_app, name="catalog")
```

Commands accept `--workspace`; JSON output uses `--format json`. Failures return a new `ExitCode.CATALOG = 9` without changing existing numeric exit codes.

- [ ] **Step 5: Test CLI and rollback paths**

Run: `uv run pytest tests/unit/catalog/test_imports.py tests/integration/catalog/test_import_publish.py tests/unit/test_cli.py -v`

Expected: PASS, including invalid workbook, missing reason, duplicate publish, and injected transaction failure.

- [ ] **Step 6: Commit the governed publication workflow**

```bash
git add src/rnaseq_mvp/catalog/imports.py src/rnaseq_mvp/catalog/cli.py src/rnaseq_mvp/cli.py src/rnaseq_mvp/constants.py tests/unit/catalog/test_imports.py tests/integration/catalog/test_import_publish.py tests/unit/test_cli.py
git commit -m "feat: publish audited public catalog releases"
```

---

### Task 5: Structured search and trustworthy result cards

**Files:**
- Create: `src/rnaseq_mvp/catalog/search.py`
- Create: `src/rnaseq_mvp/catalog/service.py`
- Create: `tests/unit/catalog/test_search.py`
- Create: `tests/integration/catalog/test_search_service.py`
- Modify: `src/rnaseq_mvp/catalog/cli.py`

**Interfaces:**
- Consumes: published catalog tables.
- Produces: `CatalogService.search(query: SearchQuery) -> list[StudyCard]`, `CatalogService.get_study(study_id) -> StudyDetail`, `CatalogService.record_discovery_request(tenant_id, project_id, requester_id, query, now) -> DiscoveryRequest`, and no-match semantics scoped to the curated catalog.

- [ ] **Step 1: Write failing structured-search tests**

```python
def test_search_filters_disease_tissue_design_and_published_release(service) -> None:
    cards = service.search(SearchQuery(
        disease=["type 2 diabetes mellitus"],
        tissue=["peripheral blood"],
        case_control_status=True,
        eligibility_status="PASS",
    ))
    assert [card.study_accession for card in cards] == ["GSE100001"]
    assert cards[0].analysis_availability in {"READY", "NOT_ANALYZED"}


def test_no_match_message_is_catalog_scoped(service) -> None:
    result = service.search(SearchQuery(disease=["no-such-term"]))
    assert result == []


def test_no_match_request_is_tenant_scoped(service) -> None:
    request = service.record_discovery_request(
        "tenant-a", "project-a", "user-a",
        SearchQuery(disease=["no-such-term"]), NOW,
    )
    assert request.status == "OPEN"
    assert service.list_discovery_requests("tenant-b") == []
```

Run: `uv run pytest tests/unit/catalog/test_search.py -v`

Expected: FAIL because search services do not exist.

- [ ] **Step 2: Implement parameterized query construction**

Use SQLite parameters exclusively. Filter normalized fields but return both raw and normalized values. Search only the latest requested `PUBLISHED` catalog release; default to the latest published release. Stable ordering is eligibility, analysis availability, sample count descending, then accession.

- [ ] **Step 3: Implement result cards and limitations**

Each `StudyCard` includes accession, title, disease, tissue, design, reported and cataloged sample counts, layout, eligibility evidence, missing fields, source URL, FASTQ state, and `READY`/`PROCESSING`/`NOT_ANALYZED` asset availability. Do not convert an empty result into a claim about all public databases.

`record_discovery_request` stores the structured no-match query under the caller's tenant and project, returns status `OPEN`, and writes an audit event. Retrieval of discovery requests is tenant-scoped; resolution requires a catalog administrator identity and a non-empty note.

- [ ] **Step 4: Add JSON CLI search**

Add `rnaseq-mvp catalog search` with repeatable `--disease`, `--tissue`, and `--layout` options plus `--case-control`, `--min-samples`, and `--format json`. Add `catalog request-discovery` requiring tenant, project, requester, and the same structured filters. These commands are contract fixtures for future WeChat integration.

- [ ] **Step 5: Verify injection resistance and tenant-free public metadata**

Run: `uv run pytest tests/unit/catalog/test_search.py tests/integration/catalog/test_search_service.py -v`

Expected: PASS; malicious filter strings return zero matches and never alter tables.

- [ ] **Step 6: Commit search services**

```bash
git add src/rnaseq_mvp/catalog/search.py src/rnaseq_mvp/catalog/service.py src/rnaseq_mvp/catalog/cli.py tests/unit/catalog/test_search.py tests/integration/catalog/test_search_service.py
git commit -m "feat: expose trusted catalog search"
```

---

### Task 6: FASTQ acquisition, verification, content addressing, and source changes

**Files:**
- Create: `src/rnaseq_mvp/catalog/raw_assets.py`
- Create: `tests/unit/catalog/test_raw_assets.py`
- Create: `tests/integration/catalog/test_raw_asset_download.py`
- Modify: `src/rnaseq_mvp/checksums.py`
- Modify: `src/rnaseq_mvp/downloader.py`

**Interfaces:**
- Consumes: published `source_file` records, HTTPX client, existing resumable downloader and checksum helpers.
- Produces: `acquire_raw_asset(source_file_version_id, workspace, repo, client, now) -> RawAssetRecord` and `verify_archived_asset(raw_asset_id, workspace, repo) -> IntegrityResult`.

- [ ] **Step 1: Write failing content-addressed archive tests**

```python
def test_two_sources_with_identical_content_share_one_archive_object(
    workspace: Path, repo: CatalogRepository, client: httpx.Client
) -> None:
    first = acquire_raw_asset("file-1", workspace, repo, client, NOW)
    second = acquire_raw_asset("file-2", workspace, repo, client, NOW)
    assert first.raw_asset_id == second.raw_asset_id
    assert repo.raw_asset_source_count(first.raw_asset_id) == 2


def test_md5_mismatch_is_quarantined_and_not_verified(
    workspace: Path, repo: CatalogRepository, client: httpx.Client
) -> None:
    with pytest.raises(RawAssetError, match="MD5 mismatch"):
        acquire_raw_asset("file-bad", workspace, repo, client, NOW)
    assert repo.source_file_state("file-bad") == "QUARANTINED"
```

Run: `uv run pytest tests/unit/catalog/test_raw_assets.py tests/integration/catalog/test_raw_asset_download.py -v`

Expected: FAIL because raw-asset services do not exist.

- [ ] **Step 2: Generalize checksum verification without weakening T2**

Expose a helper that accepts optional expected MD5 but always calculates SHA-256 and checks gzip structure:

Implement `verify_downloaded_file(path: Path, *, expected_bytes: int, expected_md5: str | None, require_gzip: bool) -> FileIntegrity`. It checks exact bytes, checks MD5 only when supplied, checks gzip by reading through EOF when required, always computes SHA-256, and returns immutable observed values plus `PASS` or `FAIL` and explicit failure codes.

Keep existing `prepare_stage` behavior requiring its frozen official MD5.

- [ ] **Step 3: Implement content-addressed promotion**

After successful verification, promote atomically to:

```text
archive/fastq/sha256/<sha256[0:2]>/<sha256>.fastq.gz
```

If the object already exists, verify it and add only a new `raw_asset_source` relation. Record download/resume/verify/archive audit events.

- [ ] **Step 4: Implement source-change detection**

When the same source accession or URL yields a new SHA-256, create a new raw asset and a `SOURCE_CONTENT_CHANGED` audit event. Never repoint an existing published analysis input silently.

- [ ] **Step 5: Run downloader regression and integration tests**

Run: `uv run pytest tests/integration/test_downloader.py tests/unit/catalog/test_raw_assets.py tests/integration/catalog/test_raw_asset_download.py -v`

Expected: PASS, including HTTP range resume, a server that ignores Range, byte overflow, MD5 mismatch, gzip corruption, and duplicate content.

- [ ] **Step 6: Commit governed public FASTQ archiving**

```bash
git add src/rnaseq_mvp/catalog/raw_assets.py src/rnaseq_mvp/checksums.py src/rnaseq_mvp/downloader.py tests/unit/catalog/test_raw_assets.py tests/integration/catalog/test_raw_asset_download.py tests/integration/test_downloader.py
git commit -m "feat: archive verified public FASTQ by content"
```

---

### Task 7: Canonical fingerprints and unique analysis jobs

**Files:**
- Create: `src/rnaseq_mvp/catalog/fingerprints.py`
- Create: `src/rnaseq_mvp/catalog/jobs.py`
- Create: `tests/unit/catalog/test_fingerprints.py`
- Create: `tests/integration/catalog/test_jobs.py`

**Interfaces:**
- Consumes: ordered verified raw assets, frozen method/reference definitions, catalog repository.
- Produces: `data_fingerprint`, `method_fingerprint`, `analysis_fingerprint`, `claim_analysis_job`, `subscribe_to_job`, and `transition_job`; reuses `canonical_json_bytes` from Task 2.

- [ ] **Step 1: Write failing canonicalization tests**

```python
def test_input_order_does_not_change_data_fingerprint() -> None:
    assert data_fingerprint([R2, R1]) == data_fingerprint([R1, R2])


def test_reference_checksum_changes_analysis_fingerprint() -> None:
    first = analysis_fingerprint(DATA, method_payload(gtf_sha="a" * 64))
    second = analysis_fingerprint(DATA, method_payload(gtf_sha="b" * 64))
    assert first != second
```

Run: `uv run pytest tests/unit/catalog/test_fingerprints.py -v`

Expected: FAIL because fingerprint functions do not exist.

- [ ] **Step 2: Implement RFC-like canonical payload rules**

Reuse `canonical_json_bytes`; reject floats in scientific identity payloads, normalize paths out of method identity, and sort input records by sample ID, assay ID, run accession, file role, then SHA-256. Hash canonical bytes with SHA-256.

- [ ] **Step 3: Write failing concurrent claim test**

```python
def test_two_claims_create_one_active_job(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim_analysis_job(repo, REQUEST, NOW), range(2)))
    assert len({result.job_id for result in results}) == 1
    assert sorted(result.created for result in results) == [False, True]
```

- [ ] **Step 4: Implement transactional job claims and transitions**

Active states are `QUEUED`, `PREPARING`, `PROCESSING`, `VALIDATING`, and `AWAITING_REVIEW`; terminal states are `PUBLISHED`, `FAILED`, and `WITHDRAWN`. Store `active_fingerprint=analysis_fingerprint` only while active. Claim uses `BEGIN IMMEDIATE`, inserts or selects the unique active job, and records each requester as a subscriber.

Define and enforce a transition map; reject state regression and require a failure reason for `FAILED`.

- [ ] **Step 5: Verify fingerprint and concurrency behavior**

Run: `uv run pytest tests/unit/catalog/test_fingerprints.py tests/integration/catalog/test_jobs.py -v`

Expected: PASS with exactly one active job under concurrent claims.

- [ ] **Step 6: Commit reusable-analysis identity and locking**

```bash
git add src/rnaseq_mvp/catalog/fingerprints.py src/rnaseq_mvp/catalog/jobs.py tests/unit/catalog/test_fingerprints.py tests/integration/catalog/test_jobs.py
git commit -m "feat: deduplicate standard analyses by fingerprint"
```

---

### Task 8: Catalog-to-pipeline preparation adapter

**Files:**
- Create: `src/rnaseq_mvp/catalog/pipeline_adapter.py`
- Create: `tests/unit/catalog/test_pipeline_adapter.py`
- Create: `tests/integration/catalog/test_catalog_prepare.py`
- Modify: `src/rnaseq_mvp/models.py`
- Modify: `src/rnaseq_mvp/prepare.py`
- Modify: `tests/unit/test_definitions.py`
- Modify: `tests/integration/test_prepare.py`

**Interfaces:**
- Consumes: a claimed job, verified archived FASTQ, existing frozen method/reference/validation definitions, and workspace.
- Produces: `CatalogAnalysisRequest`, `materialize_catalog_registry(request, base_registry) -> DefinitionRegistry`, and `prepare_catalog_analysis(request, workspace, base_registry, now) -> PreparationResult` compatible with `run_stage` and `validate_stage`.

- [ ] **Step 1: Write regression tests before generalizing definitions**

Keep all existing frozen-definition tests and add:

```python
def test_stage_accepts_catalog_identifier_but_rejects_unsafe_text() -> None:
    payload = frozen_t2a_stage_payload()
    stage = StageDefinition.model_validate(payload | {"stage_id": "CATALOG_a1b2c3d4e5f6"})
    assert stage.stage_id == "CATALOG_a1b2c3d4e5f6"
    with pytest.raises(ValueError, match="stage_id"):
        StageDefinition.model_validate(payload | {"stage_id": "../../escape"})


def test_single_end_sample_contains_only_r1() -> None:
    sample = SampleDefinition(read_layout="single-end", files=[R1])
    assert sample.files[0].role == "R1"
```

Run: `uv run pytest tests/unit/test_definitions.py tests/integration/test_prepare.py -v`

Expected: new tests FAIL while existing tests PASS.

- [ ] **Step 2: Generalize models with explicit safe validators**

Change `StageDefinition.stage_id` from a two-value literal to a string matching `^[A-Z0-9][A-Z0-9_-]{1,63}$`. Add `read_layout` to `SampleDefinition`; validate one R1 for single-end and one R1 plus one R2 for paired-end. Change `DatasetDefinition.source_database` to a non-empty controlled string accepted from the catalog, `DatasetDefinition.read_layout` to `Literal["single-end", "paired-end"]`, and `DatasetDefinition.strandedness` to `Literal["forward", "reverse", "unstranded", "auto"]`; require every sample layout to equal the dataset layout. Keep `assay="polyA plus RNA-seq"`, `library_selection="Poly(A)+"`, all method/reference literals, and current T2 YAML validity unchanged.

- [ ] **Step 3: Extract local-input preparation from `prepare_stage`**

Create this exact internal seam:

Implement `prepare_verified_inputs(*, stage_id: str, workspace: Path, registry: DefinitionRegistry, local_files: Mapping[str, Path], now: datetime) -> PreparationResult`.

`local_files` maps `file_accession` to an already verified absolute archive path. The function creates a unique run, input/reference manifests, nf-core samplesheet, parameter snapshot, and state transitions, but never downloads or mutates archived FASTQ. Existing `prepare_stage` downloads frozen inputs and delegates to the extracted primitive.

- [ ] **Step 4: Materialize an in-memory catalog registry**

`CatalogAnalysisRequest` contains the analysis fingerprint, selected assays, raw assets, reference profile ID, method profile ID, validation policy ID, and expected outputs. The adapter creates IDs `CATALOG_<fingerprint[:12]>` for stage and `PUBLIC_<fingerprint[:12]>` for dataset, and copies only approved frozen reference/method/policy objects from the base registry.

- [ ] **Step 5: Test single/paired samplesheets and archive immutability**

Run: `uv run pytest tests/unit/catalog/test_pipeline_adapter.py tests/integration/catalog/test_catalog_prepare.py tests/unit/test_definitions.py tests/integration/test_prepare.py -v`

Expected: PASS; generated samplesheets represent SE/PE correctly, archive mtimes and hashes do not change, and T2 preparation remains identical.

- [ ] **Step 6: Commit the pipeline preparation seam**

```bash
git add src/rnaseq_mvp/catalog/pipeline_adapter.py src/rnaseq_mvp/models.py src/rnaseq_mvp/prepare.py tests/unit/catalog/test_pipeline_adapter.py tests/integration/catalog/test_catalog_prepare.py tests/unit/test_definitions.py tests/integration/test_prepare.py
git commit -m "feat: prepare catalog assets for frozen workflow"
```

---

### Task 9: Immutable analysis asset publication and project references

**Files:**
- Create: `src/rnaseq_mvp/catalog/assets.py`
- Create: `tests/unit/catalog/test_assets.py`
- Create: `tests/integration/catalog/test_asset_publish.py`
- Modify: `src/rnaseq_mvp/packager.py`
- Modify: `tests/integration/test_packager.py`

**Interfaces:**
- Consumes: accepted and packaged pipeline run, analysis job, analysis fingerprint, release checksums.
- Produces: `register_published_asset`, `get_analysis_asset`, `verify_analysis_asset`, `supersede_analysis_asset`, `withdraw_analysis_asset`, `create_project_reference`, and `delete_project_reference`.

- [ ] **Step 1: Write failing publication-gate tests**

```python
def test_unreviewed_package_cannot_be_registered(repo, package_dir) -> None:
    with pytest.raises(AssetPublicationError, match="review accepted"):
        register_published_asset(repo, JOB, package_dir, actor_id="reviewer-1", now=NOW)


def test_project_deletion_does_not_delete_global_asset(service, published_asset) -> None:
    ref = service.create_project_reference("tenant-a", "project-a", published_asset.id, "user-a")
    service.delete_project_reference(ref.id, "user-a")
    assert service.get_analysis_asset(published_asset.id).status == "PUBLISHED"
    assert published_asset.package_path.exists()


def test_supersede_preserves_existing_reference(service, old_asset, new_asset) -> None:
    ref = service.create_project_reference("tenant-a", "project-a", old_asset.id, "user-a")
    service.supersede_analysis_asset(
        old_asset.id, new_asset.id, "operator-1", "new frozen method version", NOW
    )
    assert service.get_project_reference(ref.id).analysis_asset_id == old_asset.id
    assert service.get_analysis_asset(old_asset.id).status == "SUPERSEDED"
```

Run: `uv run pytest tests/unit/catalog/test_assets.py tests/integration/catalog/test_asset_publish.py -v`

Expected: FAIL because asset services do not exist.

- [ ] **Step 2: Expose package verification result**

Add:

Define `PackageIntegrity` with `status: Literal["PASS", "FAIL"]`, `checked_files: int`, and `failures: list[str]`. Implement `verify_release_package(path: Path) -> PackageIntegrity`.

Use `checksums.sha256`, reject missing, extra-required, malformed, or mismatched files, and retain existing `package_run` behavior. Extend `package_run` to publish these exact pinned nf-core/rnaseq 3.26.0 outputs: `salmon.merged.gene_counts_scaled.tsv` as `gene_counts_scaled.tsv`, `salmon.merged.gene_counts_length_scaled.tsv` as `gene_counts_length_scaled.tsv`, and `salmon.merged.gene.SummarizedExperiment.rds` as `gene_expression.SummarizedExperiment.rds`. Keep the existing raw estimated counts, TPM, gene lengths, MultiQC, manifests, parameters, validation, review, software versions, and provenance artifacts.

- [ ] **Step 3: Implement atomic immutable publication**

Copy the verified package to a temporary directory under `assets/analysis/<fingerprint[:2]>/`, fsync files, verify again, then atomically rename to `<analysis_fingerprint>`. Insert `analysis_asset` and inputs in the same logical operation; if database registration fails, remove only the new temporary/unreferenced target and leave the source release untouched.

- [ ] **Step 4: Implement tenant-scoped references and withdrawal**

Reference creation requires `PUBLISHED`, records tenant/project/user/audit fields, and is idempotent for the same tenant/project/asset. Deletion removes only the reference. `supersede_analysis_asset(old_id, new_id, actor_id, reason, now)` requires both packages to pass integrity verification, changes the old asset to `SUPERSEDED`, and preserves existing project references without silently moving them. Withdrawal requires operator identity and reason, stops new reference creation, preserves metadata and audit history, and does not silently substitute a superseding asset.

- [ ] **Step 5: Run package regressions and asset integration tests**

Run: `uv run pytest tests/integration/test_packager.py tests/unit/catalog/test_assets.py tests/integration/catalog/test_asset_publish.py -v`

Expected: PASS, including tamper detection, idempotent reference creation, tenant isolation, deletion safety, and withdrawal.

- [ ] **Step 6: Commit immutable shared assets**

```bash
git add src/rnaseq_mvp/catalog/assets.py src/rnaseq_mvp/packager.py tests/unit/catalog/test_assets.py tests/integration/catalog/test_asset_publish.py tests/integration/test_packager.py
git commit -m "feat: publish reusable immutable analysis assets"
```

---

### Task 10: End-to-end catalog execution service and operator CLI

**Files:**
- Modify: `src/rnaseq_mvp/catalog/service.py`
- Modify: `src/rnaseq_mvp/catalog/cli.py`
- Create: `tests/integration/catalog/test_catalog_end_to_end.py`
- Create: `tests/unit/catalog/test_service.py`

**Interfaces:**
- Consumes: Tasks 4–9.
- Produces: `CatalogService.request_standard_analysis`, `CatalogService.analysis_status`, `CatalogService.publish_completed_analysis`, and CLI commands `catalog acquire`, `catalog analyze`, `catalog analysis-status`, `catalog publish-asset`, `catalog link-asset`.

- [ ] **Step 1: Write a failing reuse-first service test**

```python
def test_second_request_reuses_published_asset_without_executor_call(service, executor) -> None:
    first = service.request_standard_analysis(REQUEST, requester=USER_A)
    asset = service.publish_completed_analysis(
        first.job_id, reviewer=REVIEWER, comment="accepted"
    )
    second = service.request_standard_analysis(REQUEST, requester=USER_B)
    assert second.outcome == "REUSED"
    assert second.analysis_asset_id == asset.analysis_asset_id
    assert executor.call_count == 1
```

Run: `uv run pytest tests/unit/catalog/test_service.py -v`

Expected: FAIL because orchestration methods do not exist.

- [ ] **Step 2: Implement reuse-first orchestration**

The service computes fingerprints, verifies an existing published package before reuse, otherwise claims the unique job, acquires missing raw assets, prepares the catalog run, and invokes an injected `CatalogPipelineExecutor` protocol:

Define `CatalogPipelineExecutor` as a protocol with `execute_to_review(request: CatalogAnalysisRequest, workspace: Path) -> ExecutionSummary` and `accept_and_package(stage_id: str, run_id: str, reviewer: str, comment: str, workspace: Path) -> Path`.

Production implementation wraps existing `run_stage`, `validate_stage`, `record_review`, and `package_run`. Unit tests inject a fake executor.

- [ ] **Step 3: Implement operator CLI with structured output**

Every command accepts `--workspace` and `--format text|json`. `catalog analyze` returns one of `REUSED`, `SUBSCRIBED`, `AWAITING_REVIEW`, or `FAILED`; it never auto-accepts scientific review. `catalog publish-asset` requires reviewer identity and a non-empty comment.

- [ ] **Step 4: Build a network-free end-to-end fixture**

The integration test imports and publishes a small catalog, serves tiny gzipped FASTQ through `httpx.MockTransport`, archives files, claims a job, uses a fake pipeline executor to emit a valid miniature release package, publishes it, creates references for two tenants, and proves only one executor invocation occurred.

- [ ] **Step 5: Run the full catalog suite**

Run: `uv run pytest tests/unit/catalog tests/integration/catalog -v`

Expected: PASS.

- [ ] **Step 6: Commit the end-to-end service**

```bash
git add src/rnaseq_mvp/catalog/service.py src/rnaseq_mvp/catalog/cli.py tests/unit/catalog/test_service.py tests/integration/catalog/test_catalog_end_to_end.py
git commit -m "feat: orchestrate reusable public analyses"
```

---

### Task 11: Schema export, operator documentation, safety checks, and release gate

**Files:**
- Create: `src/rnaseq_mvp/catalog/schema_export.py`
- Create: `schemas/public_catalog_study.schema.json`
- Create: `schemas/public_catalog_sample.schema.json`
- Create: `schemas/public_catalog_run_file.schema.json`
- Create: `schemas/public_catalog_eligibility.schema.json`
- Create: `docs/operations/public-catalog.md`
- Create: `tests/unit/catalog/test_schema_export.py`
- Create: `tests/unit/catalog/test_repository_safety.py`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: completed public catalog service.
- Produces: checked-in JSON schemas, curator/operator runbook, and CI release gates.

- [ ] **Step 1: Write failing schema and repository-safety tests**

```python
def test_checked_in_catalog_schemas_match_models(tmp_path: Path) -> None:
    export_catalog_schemas(tmp_path)
    for name in EXPECTED:
        assert json.loads((tmp_path / name).read_text()) == json.loads((SCHEMAS / name).read_text())


def test_repository_contains_no_sequence_or_runtime_assets() -> None:
    forbidden = {".fastq", ".fq", ".bam", ".cram", ".sra", ".part"}
    assert not [p for p in REPO.rglob("*") if any(str(p).endswith(s) for s in forbidden)]
```

Run: `uv run pytest tests/unit/catalog/test_schema_export.py tests/unit/catalog/test_repository_safety.py -v`

Expected: FAIL because exports and documentation are absent.

- [ ] **Step 2: Implement and run deterministic schema export**

Export Pydantic JSON Schema with sorted JSON keys and a final newline. Generate the four checked-in files, then rerun the equality test.

- [ ] **Step 3: Write the exact operator workflow**

Document commands for template generation, import, validation-report inspection, diff, publication, search, FASTQ acquisition, analysis request, status, human review, asset publication, project reference, integrity verification, withdrawal, backup, and recovery. Include the explicit user-facing no-match sentence: `当前平台已审核目录中未发现符合条件的数据。`

- [ ] **Step 4: Add CI coverage and README entry**

CI runs `uv run ruff check .`, `uv run pytest`, schema equality, repository safety, and secret scanning already used by the repository. Do not run full FASTQ downloads, Docker, Nextflow, or T2 analysis in GitHub Actions.

- [ ] **Step 5: Execute the release verification matrix**

Run:

```bash
uv lock --check
uv run ruff check .
uv run pytest
uv run rnaseq-mvp version
uv run rnaseq-mvp catalog --help
uv run rnaseq-mvp catalog search --workspace runtime-catalog-test --format json
git diff --check
git status --short
```

Expected: lock is current; Ruff and all tests pass; both CLIs exit successfully; empty catalog search returns an empty result with catalog-scoped semantics; no unexpected generated/runtime file is staged.

- [ ] **Step 6: Commit documentation and release gates**

```bash
git add src/rnaseq_mvp/catalog/schema_export.py schemas/public_catalog_*.schema.json docs/operations/public-catalog.md tests/unit/catalog/test_schema_export.py tests/unit/catalog/test_repository_safety.py README.md .github/workflows/ci.yml
git commit -m "docs: complete public catalog release gate"
```

---

## Final Acceptance Walkthrough

After all tasks pass, execute one manual acceptance run with a small public test dataset definition and the real frozen pipeline in an environment already validated for Docker/Nextflow:

1. Generate and populate the four-sheet workbook with non-sensitive public metadata.
2. Import it and inspect the row-addressed validation report.
3. Inspect the release diff and publish as one administrator.
4. Search by disease, tissue, design, and eligibility.
5. Acquire FASTQ and verify archive path, MD5 where supplied, gzip integrity, and SHA-256.
6. Request the standard analysis and verify it stops at `AWAITING_REVIEW`.
7. Review, package, register, and integrity-check the public asset.
8. Create project references for two separate test tenants.
9. Repeat the same analysis request and confirm the returned outcome is `REUSED` with no new Nextflow run.
10. Tamper with a copy of the release package, prove verification fails, and leave the canonical package untouched.
11. Delete one project reference and prove the other reference, global asset, and archived FASTQ remain.
12. Export the catalog release, audit events, analysis fingerprint payloads, and package checksums as the acceptance evidence bundle.

The v0.1 implementation is complete only when this walkthrough and the automated suite pass and the existing T2A/T2B behavior remains unchanged.
