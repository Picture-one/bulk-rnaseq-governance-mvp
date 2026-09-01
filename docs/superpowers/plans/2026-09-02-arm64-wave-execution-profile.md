# ARM64 Wave Execution Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separately validated `server_docker_arm64` execution path that runs nf-core/rnaseq 3.26.0 natively on Linux ARM64 through Docker and Wave-built Conda containers.

**Architecture:** Preserve the existing x86 profiles and add profile-specific architecture and network requirements. The runner and smoke command continue to use the frozen nf-core and Nextflow versions, but load an ARM-only Nextflow config enabling Wave, Conda container builds, and `linux/arm64` process architecture.

**Tech Stack:** Python 3.11, Typer, Pydantic, pytest, Nextflow 25.10.4, nf-core/rnaseq 3.26.0, Docker, Seqera Wave.

**Spec:** `docs/design/2026-09-02-arm64-wave-execution-profile.md`

## Global Constraints

- Do not modify the behavior of `server_docker` or the tag `v0.1.0-alpha.1`.
- Add the exact profile name `server_docker_arm64`.
- Accept only `aarch64` and `arm64` for the ARM server profile.
- Keep nf-core/rnaseq at `3.26.0` and Nextflow at `25.10.4`.
- Do not enable QEMU or automatic amd64 fallback.
- Keep T2A/T2B scientific definitions, references, parameters, and QC rules unchanged.
- Use TDD: run each new test red before production changes, then green before the next task.

---

### Task 1: Profile-aware preflight

**Files:**
- Modify: `src/rnaseq_mvp/preflight.py`
- Modify: `src/rnaseq_mvp/cli.py`
- Test: `tests/unit/test_preflight.py`
- Test: `tests/unit/test_preflight_cli.py`

**Interfaces:**
- Produces: `ProfileName = Literal["local_docker", "server_docker", "server_docker_arm64"]`
- Produces: `required_urls_for_profile(profile: ProfileName) -> dict[str, str]`
- Consumes: `run_preflight(profile, workspace, probe)`

- [ ] **Step 1: Write the failing architecture test**

Add a test using `StaticSystemProbe(architecture="aarch64", cpus=20, memory_gib=119, disk_free_gib=719, java_version="17.0.20", nextflow_version="25.10.4", docker_version="Docker 28.3.3", docker_hello_ok=True, reachable_urls={...all ARM endpoints True...})`.

Assert:

```python
report = run_preflight("server_docker_arm64", tmp_path, probe)
assert report.status == "PASS"
assert report.result("architecture").required == "aarch64/arm64"
```

- [ ] **Step 2: Verify the new test fails**

Run:

```bash
uv run pytest tests/unit/test_preflight.py::test_arm_server_preflight_accepts_aarch64 -v
```

Expected: FAIL with `unsupported profile: server_docker_arm64`.

- [ ] **Step 3: Implement profile-specific architecture checks**

Extend `ProfileName`, the supported-profile set, and the server failure-status branch. Compute architecture requirements as:

```python
if profile == "server_docker_arm64":
    accepted_architectures = {"aarch64", "arm64"}
    architecture_label = "aarch64/arm64"
else:
    accepted_architectures = {"x86_64", "amd64"}
    architecture_label = "x86_64"
```

Use these values in the existing `architecture` check.

- [ ] **Step 4: Add profile-specific network requirements**

Keep the current URLs as the base and add for ARM only:

```python
ARM64_REQUIRED_URLS = {
    "wave": "https://wave.seqera.io",
    "seqera_container_registry": "https://community.wave.seqera.io/v2/",
    "nextflow_registry": "https://registry.nextflow.io",
}
```

Implement `required_urls_for_profile()` without adding these endpoints to x86 profiles. Update the real probe call in the CLI so it collects the URL set for the selected profile. A `401` registry response remains reachable because `_url_reachable()` already accepts status codes below 500.

- [ ] **Step 5: Add CLI tests and run the preflight suite**

Assert `preflight --help` mentions `server_docker_arm64`, and update test probe monkeypatches to accept the profile-specific URL argument.

Run:

```bash
uv run pytest tests/unit/test_preflight.py tests/unit/test_preflight_cli.py -v
uv run ruff check src/rnaseq_mvp/preflight.py src/rnaseq_mvp/cli.py tests/unit/test_preflight.py tests/unit/test_preflight_cli.py
```

- [ ] **Step 6: Commit**

```bash
git add src/rnaseq_mvp/preflight.py src/rnaseq_mvp/cli.py tests/unit/test_preflight.py tests/unit/test_preflight_cli.py
git commit -m "feat: add ARM64-aware environment preflight"
```

---

### Task 2: ARM64 runner profile

**Files:**
- Create: `configs/profiles/server_docker_arm64.config`
- Modify: `src/rnaseq_mvp/runner.py`
- Test: `tests/unit/test_runner.py`
- Test: `tests/unit/test_frozen_assets.py`

**Interfaces:**
- Consumes: `build_nextflow_command(..., profile="server_docker_arm64", ...)`
- Produces: command loading `configs/profiles/server_docker_arm64.config`

- [ ] **Step 1: Write a failing runner test**

Call `build_nextflow_command()` with the ARM profile and assert the command retains `-profile docker`, `-r 3.26.0`, and loads `server_docker_arm64.config`.

- [ ] **Step 2: Verify red**

```bash
uv run pytest tests/unit/test_runner.py::test_arm64_command_uses_wave_profile -v
```

Expected: FAIL with `unsupported execution profile`.

- [ ] **Step 3: Extend the runner's allowed profile set**

Add `server_docker_arm64` without changing command construction for existing profiles.

- [ ] **Step 4: Write a failing frozen-config test**

Assert the new file contains all of:

```text
docker.enabled = true
wave.enabled = true
wave.strategy = ['conda']
process.arch = 'linux/arm64'
cpus: 16
memory: 60.GB
time: 72.h
```

- [ ] **Step 5: Create the ARM config**

Use:

```groovy
docker.enabled = true
wave.enabled = true
wave.strategy = ['conda']

process {
    arch = 'linux/arm64'
    resourceLimits = [
        cpus: 16,
        memory: 60.GB,
        time: 72.h
    ]
}
```

- [ ] **Step 6: Verify and commit**

```bash
uv run pytest tests/unit/test_runner.py tests/unit/test_frozen_assets.py -v
uv run ruff check src/rnaseq_mvp/runner.py tests/unit/test_runner.py tests/unit/test_frozen_assets.py
git add configs/profiles/server_docker_arm64.config src/rnaseq_mvp/runner.py tests/unit/test_runner.py tests/unit/test_frozen_assets.py
git commit -m "feat: add ARM64 Wave runner profile"
```

---

### Task 3: ARM64 smoke-test interface

**Files:**
- Modify: `src/rnaseq_mvp/smoke.py`
- Modify: `src/rnaseq_mvp/cli.py`
- Test: `tests/unit/test_smoke.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `run_smoke_test("server_docker_arm64", ...)`
- Produces: a smoke command loading `server_docker_arm64.config`

- [ ] **Step 1: Write a failing smoke command test**

Use the fake smoke executor and assert the ARM profile command includes:

```python
config_path = Path(executor.args[executor.args.index("-c") + 1])
assert config_path.name == "server_docker_arm64.config"
```

- [ ] **Step 2: Verify red**

```bash
uv run pytest tests/unit/test_smoke.py::test_arm64_smoke_uses_wave_config -v
```

Expected: FAIL with `unsupported execution profile`.

- [ ] **Step 3: Implement ARM smoke profile selection**

Accept the new profile. Load `smoke_local.config` only for `local_docker`; load `server_docker_arm64.config` for the ARM profile; do not add a config override for `server_docker`.

- [ ] **Step 4: Update CLI help test**

Assert `smoke-test --help`, `run --help`, and `execute --help` mention `server_docker_arm64`.

- [ ] **Step 5: Verify and commit**

```bash
uv run pytest tests/unit/test_smoke.py tests/unit/test_cli.py tests/unit/test_run_cli.py tests/unit/test_orchestrator.py -v
uv run ruff check src/rnaseq_mvp/smoke.py src/rnaseq_mvp/cli.py tests/unit/test_smoke.py tests/unit/test_cli.py
git add src/rnaseq_mvp/smoke.py src/rnaseq_mvp/cli.py tests/unit/test_smoke.py tests/unit/test_cli.py
git commit -m "feat: expose ARM64 Wave smoke execution"
```

---

### Task 4: Operations documentation and repository verification

**Files:**
- Modify: `README.md`
- Modify: `docs/operations/server-docker.md`

**Interfaces:**
- Produces: exact ARM install, preflight, smoke, T2A, and failure-stop commands.

- [ ] **Step 1: Document profile boundaries**

State that `server_docker` is x86_64 only and `server_docker_arm64` is ARM64 only. Document that Wave receives dependency/container build requests, while FASTQ and results remain on the server. Explicitly prohibit QEMU fallback.

- [ ] **Step 2: Document validation sequence**

Use the ordered gate: Java/Nextflow install, clone feature revision, `preflight`, small smoke-test, container architecture inspection, then T2A and T2B.

- [ ] **Step 3: Run full local verification**

```bash
uv run ruff check .
uv run python scripts/export_schemas.py --output-dir schemas
git diff --exit-code -- schemas
uv run pytest -q
uv run python scripts/check_repository_safety.py .
git diff --check
```

- [ ] **Step 4: Commit and push feature branch**

```bash
git add README.md docs/operations/server-docker.md
git commit -m "docs: add ARM64 Wave server operations"
git push origin feat/arm64-wave-profile
```

---

### Task 5: ARM server bootstrap and smoke validation

**Files:**
- Runtime only on the ARM server; do not commit FASTQ, references, work, results, credentials, or caches.

**Interfaces:**
- Consumes: GitHub branch `feat/arm64-wave-profile`
- Produces: ARM preflight JSON, smoke report JSON, counts, MultiQC, and container-architecture evidence.

- [ ] **Step 1: Install Java 17 and verify selection**

Install `openjdk-17-jre-headless`, select Java 17 with `update-alternatives`, and require `java -version` to show 17.

- [ ] **Step 2: Install exactly Nextflow 25.10.4**

Install Nextflow into `/usr/local/bin`, set `NXF_VER=25.10.4` during installation or download that release explicitly, and require `nextflow -version` to report 25.10.4.

- [ ] **Step 3: Clone the private repository and feature branch**

Authenticate with GitHub CLI or SSH, clone into `/opt/bulk-rnaseq-governance-mvp`, check out `feat/arm64-wave-profile`, and run `uv sync --frozen --extra dev`.

- [ ] **Step 4: Run ARM preflight**

```bash
uv run rnaseq-mvp preflight \
  --profile server_docker_arm64 \
  --workspace /data/rnaseq-arm/runtime
```

Expected: `PASS` for architecture, CPU, memory, disk, Java, Nextflow, Docker, Wave, Seqera registry, and Nextflow registry.

- [ ] **Step 5: Run the small ARM smoke-test**

Use local smoke assets when available; otherwise allow the nf-core test profile to retrieve public test inputs. Run with `--profile server_docker_arm64` and stop on any Wave build failure or `exec format error`.

- [ ] **Step 6: Verify evidence**

Require smoke status PASS, counts and MultiQC files, nonnegative counts, correct sample columns, and ARM64 images reported by Docker inspection. Record logs and report paths outside Git.

---

### Task 6: ARM prerelease and later T2 gates

**Files:**
- Runtime only for T2A/T2B.
- Modify documentation only if observed ARM-specific behavior must be recorded.

**Interfaces:**
- Consumes: successful ARM smoke result.
- Produces first: tag `v0.1.0-alpha.2` after the ARM smoke gate.
- Produces later: validated T2A and T2B evidence required before the formal MVP release.

- [ ] **Step 1: Final verification, merge, and tag the ARM prerelease**

After the ARM smoke-test passes, re-run the full local suite, review the branch diff against `main`, merge the validated ARM changes, and push `main`.

```bash
git tag -a v0.1.0-alpha.2 -m "ARM64 Wave smoke-tested MVP"
git push origin v0.1.0-alpha.2
```

Do not create this tag unless the ARM smoke-test and repository verification suite pass. T2A and T2B are not prerequisites for this prerelease tag; they remain prerequisites for the later formal MVP release.

- [ ] **Step 2: Run T2A after the prerelease smoke gate**

Execute the existing T2A definition with `server_docker_arm64`. Validate counts, MultiQC, scientific QC, state, and provenance. Do not proceed on warnings requiring scientific review.

- [ ] **Step 3: Run T2B only after T2A acceptance**

Use the frozen two-sample definition and repeat validation and review.

- [ ] **Step 4: Apply the formal-release gate**

Create a later formal MVP tag only after T2A and T2B both meet the agreed scientific, provenance, and reproducibility acceptance criteria.
