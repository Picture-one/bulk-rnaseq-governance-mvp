from pathlib import Path

from rnaseq_mvp import preflight as preflight_module
from rnaseq_mvp.preflight import (
    StaticSystemProbe,
    container_registry_reachable,
    run_preflight,
)


def test_server_preflight_fails_below_memory_requirement(
    tmp_path: Path,
) -> None:
    probe = StaticSystemProbe(
        system="Linux",
        architecture="x86_64",
        cpus=16,
        memory_gib=31.5,
        disk_free_gib=600,
        java_version="17.0.20",
        nextflow_version="25.10.4",
        docker_version="29.7.2",
        docker_hello_ok=True,
        reachable_urls={
            "github": True,
            "encode": True,
            "gencode": True,
            "container_registry": True,
        },
    )

    report = run_preflight(
        "server_docker",
        tmp_path,
        probe,
    )

    assert report.status == "FAIL"
    assert report.result("memory").status == "FAIL"
    assert report.result("cpu").status == "PASS"
    assert report.result("disk").status == "PASS"


def test_local_preflight_reports_resource_shortage_as_warning(
    tmp_path: Path,
) -> None:
    probe = StaticSystemProbe(
        system="Linux",
        architecture="x86_64",
        cpus=8,
        memory_gib=15.5,
        disk_free_gib=200,
        java_version="17.0.20",
        nextflow_version="25.10.4",
        docker_version="Docker version 29.7.2",
        docker_hello_ok=True,
        reachable_urls={
            "github": True,
            "encode": True,
            "gencode": True,
            "container_registry": True,
        },
    )

    report = run_preflight("local_docker", tmp_path, probe)

    assert report.status == "WARN"
    assert report.result("cpu").status == "WARN"
    assert report.result("memory").status == "WARN"
    assert report.result("disk").status == "WARN"


def test_preflight_rejects_unavailable_docker_cli(
    tmp_path: Path,
) -> None:
    probe = StaticSystemProbe(
        system="Linux",
        architecture="x86_64",
        cpus=16,
        memory_gib=64,
        disk_free_gib=500,
        java_version="17.0.20",
        nextflow_version="25.10.4",
        docker_version="unavailable: docker not found",
        docker_hello_ok=False,
        reachable_urls={
            "github": True,
            "encode": True,
            "gencode": True,
            "container_registry": True,
        },
    )

    report = run_preflight("server_docker", tmp_path, probe)

    assert report.status == "FAIL"
    assert report.result("docker_version").status == "FAIL"
    assert report.result("docker_daemon").status == "FAIL"


def test_registry_accepts_successful_docker_pull_when_wsl_https_is_blocked() -> None:
    assert container_registry_reachable(direct_http=False, docker_pull=True) is True
    assert container_registry_reachable(direct_http=False, docker_pull=False) is False
def test_arm_server_preflight_accepts_aarch64(
    tmp_path: Path,
) -> None:
    probe = StaticSystemProbe(
        system="Linux",
        architecture="aarch64",
        cpus=20,
        memory_gib=119,
        disk_free_gib=719,
        java_version="17.0.20",
        nextflow_version="25.10.4",
        docker_version="Docker version 28.3.3",
        docker_hello_ok=True,
        reachable_urls={
            "github": True,
            "encode": True,
            "gencode": True,
            "container_registry": True,
            "wave": True,
            "seqera_container_registry": True,
            "nextflow_registry": True,
        },
    )

    report = run_preflight(
        "server_docker_arm64",
        tmp_path,
        probe,
    )

    assert report.status == "PASS"
    assert report.result("architecture").required == "aarch64/arm64"
def test_arm_profile_requires_wave_endpoints() -> None:
    urls = preflight_module.required_urls_for_profile(
        "server_docker_arm64"
    )

    assert urls["wave"] == "https://wave.seqera.io"
    assert (
        urls["seqera_container_registry"]
        == "https://community.wave.seqera.io/v2/"
    )
    assert (
        urls["nextflow_registry"]
        == "https://registry.nextflow.io"
    )


def test_x86_profiles_do_not_require_wave_endpoints() -> None:
    for profile in ("local_docker", "server_docker"):
        urls = preflight_module.required_urls_for_profile(profile)

        assert "wave" not in urls
        assert "seqera_container_registry" not in urls
        assert "nextflow_registry" not in urls


def test_network_probe_accepts_reachable_redirecting_endpoint(
    httpx_mock,
) -> None:
    httpx_mock.add_response(
        method="HEAD",
        url="https://wave.seqera.io",
        status_code=301,
        headers={"Location": "https://seqera.io/wave/"},
    )

    assert preflight_module._url_reachable("https://wave.seqera.io") is True
