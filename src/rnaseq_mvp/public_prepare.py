from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx


class PublicPrepareError(RuntimeError):
    """Raised when public dataset preparation fails."""


@dataclass(frozen=True)
class PublicResolveResult:
    query_accession: str
    resolved_accession: str
    source: str


@dataclass(frozen=True)
class PublicPrepareResult:
    metadata_tsv: Path
    manifest_tsv: Path
    download_script: Path
    samplesheet_csv: Path
    params_yml: Path
    run_count: int
    fastq_count: int
    layout: str
    query_accession: str
    resolved_accession: str


ENA_FIELDS = [
    "study_accession",
    "secondary_study_accession",
    "sample_accession",
    "experiment_accession",
    "run_accession",
    "scientific_name",
    "library_strategy",
    "library_source",
    "library_selection",
    "library_layout",
    "instrument_platform",
    "instrument_model",
    "fastq_ftp",
    "fastq_md5",
    "fastq_bytes",
]


def prepare_public_dataset(
    *,
    accession: str,
    dataset: str,
    run_id: str,
    workspace: Path,
    timeout_seconds: float = 60.0,
) -> PublicPrepareResult:
    """Prepare ENA public RNA-seq inputs without downloading FASTQ files."""
    workspace = Path(workspace)
    resolved = resolve_public_accession(
        accession=accession,
        timeout_seconds=timeout_seconds,
    )

    metadata_dir = workspace / "runs" / "public_metadata"
    raw_dir = workspace / "raw" / dataset
    run_dir = workspace / "runs"

    metadata_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    rows = fetch_ena_read_run(
        accession=resolved.resolved_accession,
        timeout_seconds=timeout_seconds,
    )
    validate_ena_rows(rows)

    metadata_tsv = (
        metadata_dir / f"{dataset}_{resolved.resolved_accession}_ena_read_run.tsv"
    )
    write_ena_metadata(metadata_tsv, rows)

    manifest_tsv = raw_dir / f"{dataset}_fastq_download_manifest.tsv"
    manifest_rows = build_manifest_rows(
        rows=rows,
        dataset=dataset,
        raw_dir=raw_dir,
    )
    write_manifest(manifest_tsv, manifest_rows)

    download_script = raw_dir / f"download_{dataset}_fastq.sh"
    write_download_script(
        download_script,
        dataset=dataset,
        manifest_tsv=manifest_tsv,
        raw_dir=raw_dir,
    )

    samplesheet_csv = raw_dir / f"{dataset}_samplesheet.csv"
    layout = single_layout(rows)
    write_samplesheet(
        samplesheet_csv,
        manifest_rows=manifest_rows,
        dataset=dataset,
        layout=layout,
    )

    params_yml = run_dir / f"{run_id}_params.yml"
    write_params(
        params_yml,
        workspace=workspace,
        run_id=run_id,
        samplesheet=samplesheet_csv,
    )

    return PublicPrepareResult(
        metadata_tsv=metadata_tsv,
        manifest_tsv=manifest_tsv,
        download_script=download_script,
        samplesheet_csv=samplesheet_csv,
        params_yml=params_yml,
        run_count=len(rows),
        fastq_count=len(manifest_rows),
        layout=layout,
        query_accession=resolved.query_accession,
        resolved_accession=resolved.resolved_accession,
    )


def resolve_public_accession(
    *,
    accession: str,
    timeout_seconds: float = 60.0,
) -> PublicResolveResult:
    """Resolve a user-facing public accession to an ENA-queryable study accession."""
    normalized = accession.strip()
    if not normalized:
        raise PublicPrepareError("accession must not be empty")

    if not normalized.upper().startswith("GSE"):
        return PublicResolveResult(
            query_accession=normalized,
            resolved_accession=normalized,
            source="provided",
        )

    for resolver in (_resolve_gse_from_sra_runinfo, _resolve_gse_from_ncbi_sra_xml):
        try:
            resolved = resolver(
                gse=normalized,
                timeout_seconds=timeout_seconds,
            )
        except PublicPrepareError:
            continue
        if resolved:
            return PublicResolveResult(
                query_accession=normalized,
                resolved_accession=resolved,
                source=resolver.__name__.removeprefix("_resolve_gse_from_"),
            )

    raise PublicPrepareError(
        f"Could not resolve {normalized} to a BioProject/SRA study accession. "
        "Please provide PRJNA/SRP/ERP/PRJEB directly."
    )


def _resolve_gse_from_sra_runinfo(*, gse: str, timeout_seconds: float) -> str | None:
    url = "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo"
    try:
        response = httpx.get(
            url,
            params={"acc": gse},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PublicPrepareError(f"Failed to query SRA RunInfo for {gse}: {exc}") from exc

    text = response.text.strip()
    if not text or text.startswith("Error"):
        return None

    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return None

    projects = _unique_nonempty(row.get("BioProject", "") for row in rows)
    if projects:
        return _select_single_accession(projects, source="BioProject", query=gse)

    studies = _unique_nonempty(row.get("SRAStudy", "") for row in rows)
    if studies:
        return _select_single_accession(studies, source="SRAStudy", query=gse)

    return None


def _resolve_gse_from_ncbi_sra_xml(*, gse: str, timeout_seconds: float) -> str | None:
    ids = _ncbi_sra_esearch_ids(gse=gse, timeout_seconds=timeout_seconds)
    if not ids:
        return None

    xml_text = _ncbi_sra_efetch_xml(ids=ids, timeout_seconds=timeout_seconds)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PublicPrepareError(f"NCBI returned malformed SRA XML for {gse}: {exc}") from exc

    bioprojects: set[str] = set()
    studies: set[str] = set()
    for element in root.iter():
        tag = _strip_xml_namespace(element.tag)
        text = (element.text or "").strip()
        namespace = element.attrib.get("namespace", "")
        accession = element.attrib.get("accession", "").strip()

        if namespace == "BioProject" and text.startswith(("PRJNA", "PRJEB", "PRJDB")):
            bioprojects.add(text)
        if tag == "STUDY" and accession:
            studies.add(accession)
        if tag in {"PRIMARY_ID", "EXTERNAL_ID"} and text.startswith(("SRP", "ERP", "DRP")):
            studies.add(text)

    if bioprojects:
        return _select_single_accession(sorted(bioprojects), source="BioProject", query=gse)
    if studies:
        return _select_single_accession(sorted(studies), source="SRAStudy", query=gse)
    return None


def _ncbi_sra_esearch_ids(*, gse: str, timeout_seconds: float) -> list[str]:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    try:
        response = httpx.get(
            url,
            params={
                "db": "sra",
                "term": gse,
                "retmode": "json",
                "retmax": "100",
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PublicPrepareError(f"Failed to query NCBI SRA for {gse}: {exc}") from exc

    payload = response.json()
    return list(payload.get("esearchresult", {}).get("idlist", []))


def _ncbi_sra_efetch_xml(*, ids: list[str], timeout_seconds: float) -> str:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    try:
        response = httpx.get(
            url,
            params={"db": "sra", "id": ",".join(ids)},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PublicPrepareError(f"Failed to fetch NCBI SRA XML: {exc}") from exc
    return response.text


def fetch_ena_read_run(*, accession: str, timeout_seconds: float) -> list[dict[str, str]]:
    """Fetch ENA read_run records for a study accession such as PRJNA647610."""
    queries = [
        f'study_accession="{accession}"',
        f'secondary_study_accession="{accession}"',
    ]
    for query in queries:
        rows = _fetch_ena_read_run_query(
            query=query,
            timeout_seconds=timeout_seconds,
        )
        if rows:
            return rows

    raise PublicPrepareError(
        f"ENA returned no read_run records for accession {accession}"
    )


def _fetch_ena_read_run_query(
    *,
    query: str,
    timeout_seconds: float,
) -> list[dict[str, str]]:
    params = {
        "result": "read_run",
        "query": query,
        "fields": ",".join(ENA_FIELDS),
        "format": "tsv",
    }
    url = "https://www.ebi.ac.uk/ena/portal/api/search"

    try:
        response = httpx.get(url, params=params, timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PublicPrepareError(f"Failed to query ENA: {exc}") from exc

    text = response.text.strip()
    if not text:
        return []
    return list(csv.DictReader(text.splitlines(), delimiter="\t"))


def validate_ena_rows(rows: list[dict[str, str]]) -> None:
    required = {
        "run_accession",
        "study_accession",
        "sample_accession",
        "experiment_accession",
        "scientific_name",
        "library_strategy",
        "library_source",
        "library_layout",
        "instrument_platform",
        "fastq_ftp",
        "fastq_md5",
        "fastq_bytes",
    }

    missing_columns = required - set(rows[0])
    if missing_columns:
        raise PublicPrepareError(
            f"ENA metadata is missing columns: {sorted(missing_columns)}"
        )

    layouts = {row["library_layout"].strip().upper() for row in rows}
    if not layouts <= {"SINGLE", "PAIRED"}:
        raise PublicPrepareError(
            f"Unsupported library_layout values: {sorted(layouts)}"
        )
    if len(layouts) != 1:
        raise PublicPrepareError(
            f"Mixed library_layout values are not supported in v1: {sorted(layouts)}"
        )

    for row in rows:
        run = row["run_accession"]
        if row["scientific_name"].strip() != "Homo sapiens":
            raise PublicPrepareError(
                f"{run}: only Homo sapiens is supported, "
                f"got {row['scientific_name']!r}"
            )
        if row["library_strategy"].strip() != "RNA-Seq":
            raise PublicPrepareError(
                f"{run}: only RNA-Seq is supported, "
                f"got {row['library_strategy']!r}"
            )
        if row["library_source"].strip().upper() != "TRANSCRIPTOMIC":
            raise PublicPrepareError(
                f"{run}: only TRANSCRIPTOMIC source is supported, "
                f"got {row['library_source']!r}"
            )
        if row["instrument_platform"].strip().upper() != "ILLUMINA":
            raise PublicPrepareError(
                f"{run}: only ILLUMINA is supported, "
                f"got {row['instrument_platform']!r}"
            )
        if not row["fastq_ftp"].strip():
            raise PublicPrepareError(f"{run}: missing fastq_ftp")
        if not row["fastq_md5"].strip():
            raise PublicPrepareError(f"{run}: missing fastq_md5")
        if not row["fastq_bytes"].strip():
            raise PublicPrepareError(f"{run}: missing fastq_bytes")


def single_layout(rows: list[dict[str, str]]) -> str:
    return rows[0]["library_layout"].strip().upper()


def write_ena_metadata(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENA_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def build_manifest_rows(
    *,
    rows: list[dict[str, str]],
    dataset: str,
    raw_dir: Path,
) -> list[dict[str, str]]:
    manifest_rows: list[dict[str, str]] = []

    for row in sorted(rows, key=lambda item: item["run_accession"]):
        run = row["run_accession"]
        urls = row["fastq_ftp"].split(";")
        md5s = row["fastq_md5"].split(";")
        sizes = row["fastq_bytes"].split(";")
        layout = row["library_layout"].strip().upper()

        expected_files = 2 if layout == "PAIRED" else 1
        if not (len(urls) == len(md5s) == len(sizes) == expected_files):
            raise PublicPrepareError(
                f"{run}: expected {expected_files} FASTQ files for {layout}, "
                f"got urls={len(urls)}, md5s={len(md5s)}, sizes={len(sizes)}"
            )

        roles = ["R1", "R2"] if layout == "PAIRED" else ["SE"]
        for role, url, md5, size in zip(roles, urls, md5s, sizes, strict=True):
            file_name = url.rstrip("/").split("/")[-1]
            https_url = "https://" + url.removeprefix("https://").removeprefix("http://")
            manifest_rows.append(
                {
                    "study_accession": dataset,
                    "sample_accession": row["sample_accession"],
                    "experiment_accession": row["experiment_accession"],
                    "run_accession": run,
                    "file_role": role,
                    "file_name": file_name,
                    "download_url": https_url,
                    "expected_bytes": size,
                    "expected_md5": md5,
                    "local_path": str(raw_dir / file_name),
                }
            )

    return manifest_rows


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "study_accession",
        "sample_accession",
        "experiment_accession",
        "run_accession",
        "file_role",
        "file_name",
        "download_url",
        "expected_bytes",
        "expected_md5",
        "local_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_download_script(
    path: Path,
    *,
    dataset: str,
    manifest_tsv: Path,
    raw_dir: Path,
) -> None:
    script = f'''#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="{raw_dir}"
MANIFEST="{manifest_tsv}"

mkdir -p "${{BASE_DIR}}"
cd "${{BASE_DIR}}"

if [ ! -f "${{MANIFEST}}" ]; then
  echo "Manifest not found: ${{MANIFEST}}" >&2
  exit 1
fi

echo "Downloading FASTQ files listed in ${{MANIFEST}}"

tail -n +2 "${{MANIFEST}}" | while IFS=$'\t' read -r study sample experiment run role file_name url expected_bytes expected_md5 local_path; do
  echo "==> ${{file_name}}"

  if [ -f "${{file_name}}" ]; then
    echo "    exists, skip download"
  else
    wget -c -O "${{file_name}}" "${{url}}"
  fi

  actual_bytes="$(stat -c%s "${{file_name}}")"
  if [ "${{actual_bytes}}" != "${{expected_bytes}}" ]; then
    echo "Size mismatch for ${{file_name}}: expected ${{expected_bytes}}, got ${{actual_bytes}}" >&2
    exit 2
  fi

  echo "${{expected_md5}}  ${{file_name}}" | md5sum -c -
done

echo "All {dataset} FASTQ files downloaded and verified."
'''
    path.write_text(script, encoding="utf-8")


def write_samplesheet(
    path: Path,
    *,
    manifest_rows: list[dict[str, str]],
    dataset: str,
    layout: str,
) -> None:
    by_run: dict[str, dict[str, str]] = {}
    for row in manifest_rows:
        by_run.setdefault(row["run_accession"], {})[row["file_role"]] = row["local_path"]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if layout == "PAIRED":
            writer.writerow([
                "sample",
                "fastq_1",
                "fastq_2",
                "strandedness",
                "seq_platform",
                "seq_center",
            ])
            for run in sorted(by_run):
                files = by_run[run]
                if "R1" not in files or "R2" not in files:
                    raise PublicPrepareError(
                        f"{run}: paired samplesheet requires both R1 and R2"
                    )
                writer.writerow([
                    f"{dataset}_{run}",
                    files["R1"],
                    files["R2"],
                    "auto",
                    "ILLUMINA",
                    "unknown",
                ])
        elif layout == "SINGLE":
            writer.writerow([
                "sample",
                "fastq_1",
                "strandedness",
                "seq_platform",
                "seq_center",
            ])
            for run in sorted(by_run):
                files = by_run[run]
                if "SE" not in files:
                    raise PublicPrepareError(
                        f"{run}: single-end samplesheet requires SE"
                    )
                writer.writerow([
                    f"{dataset}_{run}",
                    files["SE"],
                    "auto",
                    "ILLUMINA",
                    "unknown",
                ])
        else:
            raise PublicPrepareError(f"Unsupported layout: {layout}")


def write_params(
    path: Path,
    *,
    workspace: Path,
    run_id: str,
    samplesheet: Path,
) -> None:
    text = f'''input: {samplesheet}
outdir: {workspace / "results" / run_id}
fasta: {workspace / "reference" / "human_grch38_gencode_v50_primary" / "GRCh38.primary_assembly.genome.fa.gz"}
gtf: {workspace / "reference" / "human_grch38_gencode_v50_primary" / "gencode.v50.primary_assembly.annotation.gtf.gz"}
gencode: true
gtf_extra_attributes: "gene_name,gene_type"
featurecounts_group_type: "gene_type"
igenomes_ignore: true
pseudo_aligner: salmon
skip_alignment: true
skip_bigwig: true
skip_stringtie: true
skip_deseq2_qc: true
'''
    path.write_text(text, encoding="utf-8")


def _unique_nonempty(values: object) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _select_single_accession(values: list[str], *, source: str, query: str) -> str:
    if len(values) == 1:
        return values[0]
    raise PublicPrepareError(
        f"{query} resolved to multiple {source} accessions: {', '.join(values)}. "
        "Please provide the desired accession directly."
    )


def _strip_xml_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag
