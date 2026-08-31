from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SafetyFinding:
    rule: str
    path: Path
    detail: str


_IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "runtime",
    "work",
    "results",
    "release",
}
_FORBIDDEN_SUFFIXES = (
    ".fastq",
    ".fastq.gz",
    ".fq",
    ".fq.gz",
    ".bam",
    ".cram",
    ".fa",
    ".fa.gz",
    ".fasta",
    ".fasta.gz",
    ".fna",
    ".fna.gz",
    ".gtf",
    ".gtf.gz",
    ".gff",
    ".gff3",
)
_SECRET_FILENAMES = {".env", "id_rsa", "id_dsa", "id_ed25519"}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
_GENERIC_CREDENTIAL = re.compile(
    r"(?i)(?:password|passwd|api[_-]?key|access[_-]?token|token)"
    r"\s*[:=]\s*[\"']?([^\s\"']{8,})"
)
_PLACEHOLDER_MARKERS = ("secret", "example", "dummy", "placeholder", "redacted", "test")
_PATIENT_COLUMNS = {
    "patient_id",
    "patient_name",
    "medical_record_number",
    "mrn",
    "id_card",
    "身份证号",
    "住院号",
}


def _files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        yield path


def _patient_header(path: Path) -> set[str]:
    if path.suffix.lower() not in {".csv", ".tsv"}:
        return set()
    try:
        first_line = path.open("r", encoding="utf-8").readline().strip()
    except UnicodeDecodeError:
        return set()
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    columns = {column.strip().lower() for column in first_line.split(delimiter)}
    return columns & _PATIENT_COLUMNS


def scan_repository(root: Path) -> list[SafetyFinding]:
    root = root.resolve()
    findings: list[SafetyFinding] = []
    for path in _files(root):
        relative = path.relative_to(root)
        lowered = path.name.lower()
        if lowered.endswith(_FORBIDDEN_SUFFIXES):
            findings.append(
                SafetyFinding("forbidden_data", relative, "omics data/reference file")
            )
            continue
        if lowered in _SECRET_FILENAMES or lowered.endswith((".pem", ".key")):
            findings.append(SafetyFinding("secret_file", relative, "secret-like filename"))
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            findings.append(
                SafetyFinding("oversized_file", relative, "file exceeds 10 MiB")
            )
            continue
        patient_columns = _patient_header(path)
        if patient_columns:
            findings.append(
                SafetyFinding(
                    "patient_identifier",
                    relative,
                    f"identifier columns: {','.join(sorted(patient_columns))}",
                )
            )
            continue
        if path.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".json", ".toml"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        generic_matches = _GENERIC_CREDENTIAL.findall(content)
        has_nonplaceholder_credential = any(
            not any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS)
            for value in generic_matches
        )
        if any(pattern.search(content) for pattern in _SECRET_PATTERNS) or (
            has_nonplaceholder_credential
        ):
            findings.append(
                SafetyFinding("credential_pattern", relative, "credential-like content")
            )
    return sorted(findings, key=lambda finding: (str(finding.path), finding.rule))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repository for unsafe files")
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    findings = scan_repository(args.root)
    for finding in findings:
        print(f"{finding.rule}\t{finding.path}\t{finding.detail}")
    if findings:
        print(f"Repository safety scan failed: {len(findings)} finding(s)")
        return 1
    print("Repository safety scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
