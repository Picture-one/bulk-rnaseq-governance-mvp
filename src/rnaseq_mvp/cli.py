import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
import typer

from rnaseq_mvp.constants import MVP_VERSION, ExitCode
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.downloader import DownloadError
from rnaseq_mvp.orchestrator import (
    RealExecutionServices,
    execute_stage,
    stage_status,
)
from rnaseq_mvp.packager import PackageError, package_run
from rnaseq_mvp.preflight import (
    RealSystemProbe,
    run_preflight,
    write_preflight_report,
)
from rnaseq_mvp.prepare import PreparationError, prepare_stage
from rnaseq_mvp.reviewer import ReviewError, record_review
from rnaseq_mvp.runner import (
    IntegrityError,
    PipelineRunError,
    RealProcessExecutor,
    run_stage,
)
from rnaseq_mvp.smoke import run_smoke_test
from rnaseq_mvp.validator import ValidationError, validate_stage

DEFAULT_WORKSPACE = Path("runtime")
app = typer.Typer(
    name="rnaseq-mvp",
    help="Governed Bulk RNA-seq FASTQ-to-counts MVP.",
    no_args_is_help=True,
    add_completion=False,
)


def _not_implemented() -> None:
    typer.echo("not implemented in this milestone")
    raise typer.Exit(code=int(ExitCode.CONFIG))


@app.command()
def version() -> None:
    """Show the MVP version."""
    typer.echo(f"rnaseq-mvp {MVP_VERSION}")


@app.command()
def preflight(
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="Execution profile: local_docker or server_docker.",
        ),
    ] = "local_docker",
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            help="Runtime workspace directory.",
        ),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Check the execution environment."""
    try:
        probe = RealSystemProbe.collect(workspace)
        report = run_preflight(
            profile,
            workspace,
            probe,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(
            code=int(ExitCode.CONFIG)
        ) from error

    report_path = write_preflight_report(
        report,
        workspace,
    )

    typer.echo(
        f"Preflight status: {report.status}"
    )

    for check in report.checks:
        typer.echo(
            f"{check.name}\t"
            f"{check.status}\t"
            f"{check.observed}\t"
            f"{check.required}"
        )

    typer.echo(f"Report: {report_path}")

    if report.status == "FAIL":
        raise typer.Exit(
            code=int(ExitCode.PREFLIGHT)
        )


@app.command()
def prepare(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Download and verify frozen inputs."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        registry = DefinitionRegistry.load(repo_root / "definitions")
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=20.0),
        ) as client:
            result = prepare_stage(
                stage.upper(),
                workspace,
                registry,
                client,
                datetime.now(timezone.utc),
            )
    except (KeyError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG)) from error
    except (DownloadError, PreparationError, httpx.HTTPError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.PREPARE)) from error

    typer.echo(f"Preparation status: {result.status}")
    typer.echo(f"Run ID: {result.run_id}")
    typer.echo(f"Input manifest: {result.input_manifest_path}")
    typer.echo(f"Reference manifest: {result.reference_manifest_path}")
    typer.echo(f"Samplesheet: {result.samplesheet_path}")
    typer.echo(f"Parameters: {result.parameters_path}")


@app.command()
def run(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Prepared run identifier."),
    ],
    profile: Annotated[
        str,
        typer.Option(
            "--profile", help="Execution profile: local_docker or server_docker."
        ),
    ] = "server_docker",
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
    resume: Annotated[
        bool,
        typer.Option("--resume/--no-resume", help="Allow Nextflow cache resume."),
    ] = True,
) -> None:
    """Run the pinned nf-core workflow."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        registry = DefinitionRegistry.load(repo_root / "definitions")
        result = run_stage(
            stage.upper(),
            run_id,
            profile,
            workspace,
            registry,
            RealProcessExecutor(),
            resume,
        )
    except (KeyError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG)) from error
    except (IntegrityError, PipelineRunError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.RUN)) from error

    typer.echo(f"Run status: {result.status}")
    typer.echo(f"Run ID: {result.run_id}")
    typer.echo(f"Provenance: {result.provenance_path}")
    typer.echo(f"Stdout: {result.stdout_path}")
    typer.echo(f"Stderr: {result.stderr_path}")


@app.command()
def validate(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Executed run identifier."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Validate counts, QC, and provenance."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        registry = DefinitionRegistry.load(repo_root / "definitions")
        report = validate_stage(stage.upper(), run_id, workspace, registry)
    except (KeyError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG)) from error
    except (ValidationError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.VALIDATE)) from error

    typer.echo(f"Validation status: {report.status}")
    typer.echo(f"Counts: {report.counts_path}")
    typer.echo(f"Reference traceability: {report.reference_traceability}")
    typer.echo(f"Report: {workspace / 'runs' / run_id / 'validation_report.json'}")


@app.command()
def review(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    run_id: Annotated[str, typer.Option("--run-id", help="Validated run identifier.")],
    reviewer: Annotated[str, typer.Option("--reviewer", help="Reviewer identity.")],
    decision: Annotated[
        str,
        typer.Option("--decision", help="Review decision: accept or reject."),
    ],
    comment: Annotated[
        str,
        typer.Option("--comment", help="Required scientific review comment."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Record the human review decision."""
    normalized_decision = decision.lower()
    if normalized_decision not in {"accept", "reject"}:
        typer.echo("decision must be accept or reject", err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG))
    try:
        record = record_review(
            stage.upper(),
            run_id,
            reviewer,
            normalized_decision,
            comment,
            workspace,
            datetime.now(timezone.utc),
        )
    except (ReviewError, FileExistsError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.REVIEW)) from error
    typer.echo(f"Review decision: {record.decision}")
    typer.echo(f"Reviewer: {record.reviewer}")
    typer.echo(f"Record: {workspace / 'runs' / run_id / 'review_record.json'}")


@app.command(name="package")
def package_command(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Accepted run identifier."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Create a governed release package."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        registry = DefinitionRegistry.load(repo_root / "definitions")
        result = package_run(stage.upper(), run_id, workspace, registry)
    except (KeyError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG)) from error
    except (PackageError, FileExistsError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.PACKAGE)) from error
    typer.echo(f"Release status: {result.status}")
    typer.echo(f"Release directory: {result.release_directory}")
    typer.echo(f"Checksums: {result.checksums_path}")


@app.command()
def status(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text or json."),
    ] = "text",
) -> None:
    """Show stage and run status."""
    if output_format not in {"text", "json"}:
        typer.echo("format must be text or json", err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG))
    summary = stage_status(stage.upper(), workspace)
    if output_format == "json":
        typer.echo(json.dumps(summary.model_dump(mode="json"), sort_keys=True))
        return
    typer.echo(f"Stage: {summary.stage_id}")
    typer.echo(f"Run ID: {summary.run_id or '-'}")
    typer.echo(f"Status: {summary.status}")
    typer.echo(f"Last error: {summary.last_error or '-'}")
    typer.echo(f"Next action: {summary.next_action}")
    typer.echo(f"Release allowed: {str(summary.release_allowed).lower()}")


@app.command()
def execute(
    stage: Annotated[
        str,
        typer.Option("--stage", help="Frozen scientific stage, for example T2A."),
    ],
    profile: Annotated[
        str,
        typer.Option(
            "--profile", help="Execution profile: local_docker or server_docker."
        ),
    ] = "server_docker",
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Run the automated workflow up to human review."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        registry = DefinitionRegistry.load(repo_root / "definitions")
        summary = execute_stage(
            stage.upper(),
            profile,
            workspace,
            RealExecutionServices(registry),
        )
    except (KeyError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.CONFIG)) from error
    except (DownloadError, PreparationError, httpx.HTTPError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.PREPARE)) from error
    except (IntegrityError, PipelineRunError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.RUN)) from error
    except ValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.VALIDATE)) from error
    typer.echo(f"Execution status: {summary.status}")
    if summary.run_id:
        typer.echo(f"Run ID: {summary.run_id}")
    if summary.status == "PREFLIGHT_FAILED":
        raise typer.Exit(code=int(ExitCode.PREFLIGHT))
    if summary.status == "VALIDATION_FAILED":
        raise typer.Exit(code=int(ExitCode.VALIDATE))


@app.command(name="smoke-test")
def smoke_test(
    profile: Annotated[
        str,
        typer.Option(
            "--profile", help="Execution profile: local_docker or server_docker."
        ),
    ] = "local_docker",
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Runtime workspace directory."),
    ] = DEFAULT_WORKSPACE,
    assets_manifest: Annotated[
        Path | None,
        typer.Option(
            "--assets-manifest",
            help="YAML manifest containing local nf-core smoke-test assets.",
        ),
    ] = None,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Start a new Nextflow session instead of resuming the previous one.",
        ),
    ] = False,
) -> None:
    """Run the small nf-core toolchain smoke test."""
    try:
        result = run_smoke_test(
            profile,
            workspace,
            RealProcessExecutor(),
            resume=not fresh,
            assets_manifest=assets_manifest,
        )
    except (ValueError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=int(ExitCode.RUN)) from error
    typer.echo(f"Smoke status: {result.status}")
    typer.echo(f"Report: {result.report_path}")
    typer.echo(f"Results: {result.outdir}")
    if result.status == "FAIL":
        typer.echo(f"Missing outputs: {','.join(result.missing_outputs)}", err=True)
        raise typer.Exit(code=int(ExitCode.RUN))
