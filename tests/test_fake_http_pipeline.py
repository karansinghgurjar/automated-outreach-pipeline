from pathlib import Path
import socket
import subprocess
import sys
import time

import requests

from app.pipeline import OutreachPipeline


def wait_for_server(host: str, port: int, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.post(
                f"http://{host}:{port}/ocean/lookalikes",
                json={"domain": "notion.so"},
                timeout=1,
            )
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                time.sleep(0.1)
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for fake API server on {host}:{port}.")


def start_fake_server(project_root: Path, port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fake_api_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for_server("127.0.0.1", port)
    return process


def build_fake_http_pipeline(
    tmp_path,
    monkeypatch,
    port: int,
    fail_mode: str = "",
) -> OutreachPipeline:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FAKE_API_BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("FAKE_API_FAIL_MODE", fail_mode)
    return OutreachPipeline(
        seed_domain="notion.so",
        service_modes={
            "ocean": "fake_http",
            "prospeo": "fake_http",
            "eazyreach": "fake_http",
            "brevo": "fake_http",
        },
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=True,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )


def test_fake_http_mode_pipeline_completes(tmp_path, monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    port = 8011
    server = start_fake_server(project_root, port)
    try:
        summary = build_fake_http_pipeline(tmp_path, monkeypatch, port).run()
    finally:
        server.terminate()
        server.wait(timeout=10)

    assert summary.companies_found == 3
    assert summary.contacts_found == 3
    assert summary.verified_emails == 3
    assert summary.dry_run is True


def test_fake_http_429_is_handled(tmp_path, monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    port = 8012
    server = start_fake_server(project_root, port)
    try:
        summary = build_fake_http_pipeline(tmp_path, monkeypatch, port, fail_mode="rate_limit").run()
    finally:
        server.terminate()
        server.wait(timeout=10)

    assert summary.ocean_status["status"] == "failed"
    assert summary.contacts_found == 0
    assert summary.emails_sent == 0


def test_fake_http_500_is_handled(tmp_path, monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    port = 8013
    server = start_fake_server(project_root, port)
    try:
        summary = build_fake_http_pipeline(tmp_path, monkeypatch, port, fail_mode="server").run()
    finally:
        server.terminate()
        server.wait(timeout=10)

    assert summary.ocean_status["status"] == "failed"
    assert summary.verified_emails == 0


def test_fake_http_empty_result_does_not_crash(tmp_path, monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    port = 8014
    server = start_fake_server(project_root, port)
    try:
        summary = build_fake_http_pipeline(tmp_path, monkeypatch, port, fail_mode="empty").run()
    finally:
        server.terminate()
        server.wait(timeout=10)

    assert summary.companies_found == 0
    assert summary.contacts_found == 0
    assert summary.verified_emails == 0
