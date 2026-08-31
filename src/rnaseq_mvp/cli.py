from pathlib import Path
from typing import Annotated

import typer

from rnaseq_mvp.constants import MVP_VERSION, ExitCode
from rnaseq_mvp.preflight import (
    RealSystemProbe,
    run_preflight,
    write_preflight_report,
)

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
def prepare() -> None:
    """Download and verify frozen inputs."""
    _not_implemented()


@app.command()
def run() -> None:
    """Run the pinned nf-core workflow."""
    _not_implemented()


@app.command()
def validate() -> None:
    """Validate counts, QC, and provenance."""
    _not_implemented()


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
