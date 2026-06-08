from __future__ import annotations

from app.models import EmailMessage, VerifiedContact
from app.pipeline import OutreachPipeline
from app.services.brevo import BrevoService

import pytest


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


def build_verified_contact(email: str = "sarah@airtable.com") -> VerifiedContact:
    return VerifiedContact(
        name="Sarah Chen",
        title="VP Growth",
        company_name="Airtable",
        company_domain="airtable.com",
        linkedin_url="https://linkedin.com/in/sarah-chen",
        email=email,
        verification_status="verified",
    )


def build_message(email: str = "sarah@airtable.com") -> EmailMessage:
    return EmailMessage(
        contact_name="Sarah Chen",
        company_domain="airtable.com",
        recipient_email=email,
        subject="Demo outreach",
        body="Hello from the demo pipeline.",
    )


def build_live_brevo_service() -> BrevoService:
    return BrevoService(
        mode="live",
        sender_email="sender@example.com",
        sender_name="Sender Example",
        api_key="test-brevo-key",
        timeout_seconds=0.1,
        max_retries=3,
    )


def test_live_brevo_missing_api_key_fails_clearly() -> None:
    service = BrevoService(
        mode="live",
        sender_email="sender@example.com",
        sender_name="Sender Example",
        api_key="",
    )

    with pytest.raises(ValueError, match="BREVO_API_KEY"):
        service.send_outreach([build_verified_contact()], [build_message()], dry_run=False)


def test_live_brevo_401_is_reported_per_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.brevo.requests.post",
        lambda *args, **kwargs: FakeResponse(401, {"message": "Unauthorized"}),
    )
    service = build_live_brevo_service()

    results = service.send_outreach([build_verified_contact()], [build_message()], dry_run=False)

    assert len(results) == 1
    assert results[0].send_status == "failed"
    assert "401" in (results[0].failure_reason or "")


def test_live_brevo_429_is_retried(monkeypatch) -> None:
    attempts = {"count": 0}

    def fake_post(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return FakeResponse(429, {"message": "Rate limited"})
        return FakeResponse(201, {"messageId": "msg-123"})

    monkeypatch.setattr("app.services.brevo.requests.post", fake_post)
    service = build_live_brevo_service()

    results = service.send_outreach([build_verified_contact()], [build_message()], dry_run=False)

    assert attempts["count"] == 3
    assert results[0].send_status == "sent"
    assert results[0].provider_message_id == "msg-123"


def test_one_failed_email_does_not_crash_remaining_sends(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse(400, {"message": "Bad request"})
        return FakeResponse(201, {"messageId": "msg-456"})

    monkeypatch.setattr("app.services.brevo.requests.post", fake_post)
    service = build_live_brevo_service()
    contacts = [build_verified_contact("first@airtable.com"), build_verified_contact("second@airtable.com")]
    messages = [build_message("first@airtable.com"), build_message("second@airtable.com")]

    results = service.send_outreach(contacts, messages, dry_run=False)

    assert len(results) == 2
    assert results[0].send_status == "failed"
    assert results[1].send_status == "sent"


def test_live_brevo_dry_run_does_not_hit_network(monkeypatch) -> None:
    def fail_post(*args, **kwargs):
        raise AssertionError("Network should not be called during dry-run.")

    monkeypatch.setattr("app.services.brevo.requests.post", fail_post)
    service = build_live_brevo_service()

    results = service.send_outreach([build_verified_contact()], [build_message()], dry_run=True)

    assert len(results) == 1
    assert results[0].send_status == "dry_run"


def test_pipeline_blocks_mock_verified_emails_from_live_send(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("BREVO_SENDER_NAME", "Sender Example")
    pipeline = OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": "csv", "prospeo": "mock", "eazyreach": "mock", "brevo": "live"},
        limit_companies=3,
        limit_contacts=6,
        max_contacts_per_company=2,
        dry_run=False,
        simulate_failures=False,
        timeout_seconds=0.1,
        max_retries=2,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=True,
    )

    summary = pipeline.run()

    assert summary.brevo_mode == "live"
    assert summary.blocked_unverified_count > 0
    assert summary.emails_sent == 0
    assert summary.brevo_status["status"] == "blocked"
    assert summary.send_decision == "blocked_unverified"
