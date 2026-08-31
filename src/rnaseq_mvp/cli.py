from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
import typer

from rnaseq_mvp.constants import MVP_VERSION, ExitCode
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.downloader import DownloadError
from rnaseq_mvp.preflight import (
    RealSystemProbe,
    run_preflight,
    write_preflight_report,
)
from rnaseq_mvp.prepare import PreparationError, prepare_stage
from rnaseq_mvp.runner import (
    IntegrityError,
    PipelineRunError,
    RealProcessExecutor,
    run_stage,
)
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
def review() -> None:
    """Record the human review decision."""
    _not_implemented()


@app.command(name="package")
def package_command() -> None:
    """Create a governed release package."""
    _not_implemented()


@app.command()
def status() -> None:
    """Show stage and run status."""
    _not_implemented()


@app.command()
def execute() -> None:
    """Run the automated workflow up to human review."""
    _not_implemented()


@app.command(name="smoke-test")
def smoke_test() -> None:
    """Run the small nf-core toolchain smoke test."""
    _not_implemented()
