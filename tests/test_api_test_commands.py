from __future__ import annotations

from app.services.brevo import BrevoService
from app.services.ocean import OceanService
from app.services.prospeo import ProspeoService
from main import build_parser, run_check_env

import pytest


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


def test_parser_allows_api_test_without_domain() -> None:
    parser = build_parser()
    args = parser.parse_args(["--test-prospeo"])

    assert args.domain is None
    assert args.test_prospeo is True


def test_parser_allows_check_env_without_domain() -> None:
    parser = build_parser()
    args = parser.parse_args(["--check-env"])

    assert args.domain is None
    assert args.check_env is True


def test_check_env_prints_present_missing_only(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OCEAN_API_KEY", "secret-ocean")
    monkeypatch.delenv("PROSPEO_API_KEY", raising=False)
    monkeypatch.setenv("BREVO_API_KEY", "secret-brevo")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.delenv("BREVO_SENDER_NAME", raising=False)

    run_check_env()
    output = capsys.readouterr().out

    assert "OCEAN_API_KEY: present" in output
    assert "PROSPEO_API_KEY: missing" in output
    assert "BREVO_API_KEY: present" in output
    assert "secret-ocean" not in output
    assert "secret-brevo" not in output


def test_ocean_test_connection_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OCEAN_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Missing OCEAN_API_KEY"):
        OceanService(mode="mock").test_connection()


def test_ocean_403_shows_csv_fallback_message(monkeypatch) -> None:
    monkeypatch.setenv("OCEAN_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ocean.requests.get",
        lambda *args, **kwargs: FakeResponse(403, {"detail": "forbidden"}),
    )

    with pytest.raises(ValueError, match="Use --source csv until Ocean API access is resolved"):
        OceanService(mode="mock").test_connection()


def test_prospeo_test_connection_success(monkeypatch) -> None:
    monkeypatch.setenv("PROSPEO_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.prospeo.requests.get",
        lambda *args, **kwargs: FakeResponse(
            200,
            {
                "error": False,
                "response": {
                    "current_plan": "STARTER",
                    "remaining_credits": 99,
                    "used_credits": 1,
                },
            },
        ),
    )

    result = ProspeoService(mode="mock").test_connection()

    assert result["status"] == "ok"
    assert result["current_plan"] == "STARTER"
    assert result["remaining_credits"] == 99


def test_brevo_test_connection_missing_sender(monkeypatch) -> None:
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.delenv("BREVO_SENDER_EMAIL", raising=False)
    monkeypatch.delenv("BREVO_SENDER_NAME", raising=False)

    service = BrevoService(mode="live", api_key="test-key", sender_email="", sender_name="")
    with pytest.raises(ValueError, match="Missing BREVO_SENDER_EMAIL"):
        service.test_connection()


def test_brevo_test_connection_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.brevo.requests.get",
        lambda *args, **kwargs: FakeResponse(
            200,
            {
                "email": "owner@example.com",
                "companyName": "Example Co",
                "plan": [{"type": "free"}],
            },
        ),
    )
    service = BrevoService(
        mode="live",
        api_key="test-key",
        sender_email="sender@example.com",
        sender_name="Sender",
    )

    result = service.test_connection()

    assert result["status"] == "ok"
    assert result["sender_email_configured"] == "sender@example.com"
    assert result["sender_name_configured"] == "Sender"
