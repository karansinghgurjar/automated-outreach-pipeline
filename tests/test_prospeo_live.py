from __future__ import annotations

from typing import Any

from app.pipeline import OutreachPipeline
from app.services.prospeo import PROSPEO_SEARCH_PERSON_URL

import pytest


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload


def build_live_prospeo_pipeline(
    tmp_path,
    monkeypatch,
    source: str = "csv",
) -> OutreachPipeline:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROSPEO_API_KEY", "test-prospeo-key")
    return OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": source, "prospeo": "live", "eazyreach": "skipped", "brevo": "mock"},
        limit_companies=3,
        limit_contacts=10,
        max_contacts_per_company=2,
        dry_run=True,
        simulate_failures=False,
        timeout_seconds=0.1,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )


def build_search_payload(company_domain: str, full_name: str) -> dict[str, Any]:
    return {
        "error": False,
        "results": [
            {
                "person": {
                    "id": f"id-{company_domain}",
                    "full_name": full_name,
                    "current_job_title": "VP Engineering",
                    "linkedin_url": f"https://www.linkedin.com/in/{full_name.lower().replace(' ', '-')}",
                },
                "company": {
                    "name": company_domain.split(".")[0].title(),
                    "domain": company_domain,
                },
            }
        ],
        "pagination": {
            "current_page": 1,
            "total_page": 1,
        },
    }


def build_enrich_payload(email: str | None) -> dict[str, Any]:
    return {
        "error": False,
        "person": {
            "email": {
                "status": "VERIFIED" if email else "UNAVAILABLE",
                "email": email,
            }
        },
    }


def extract_company_domain(kwargs: dict[str, Any]) -> str:
    company_filter = kwargs["json"]["filters"]["company"]["websites"]["include"][0]
    return str(company_filter)


def test_live_prospeo_pipeline_completes(tmp_path, monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        if args[0] == PROSPEO_SEARCH_PERSON_URL:
            company_domain = extract_company_domain(kwargs)
            return FakeResponse(200, build_search_payload(company_domain, f"Sarah {company_domain.split('.')[0].title()}"))
        return FakeResponse(200, build_enrich_payload("sarah.chen@example.com"))

    monkeypatch.setattr("app.services.prospeo.requests.post", fake_post)

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.prospeo_mode == "live"
    assert summary.contacts_found == 3
    assert summary.prospeo_emails_found == 3
    assert summary.companies_with_contacts == 3
    assert summary.companies_failed == 0
    assert summary.prospeo_status["status"] == "success"


def test_live_prospeo_missing_api_key_fails_preflight(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PROSPEO_API_KEY", raising=False)
    pipeline = OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": "csv", "prospeo": "live", "eazyreach": "skipped", "brevo": "mock"},
        limit_companies=3,
        limit_contacts=10,
        max_contacts_per_company=2,
        dry_run=True,
        simulate_failures=False,
        timeout_seconds=0.1,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )

    with pytest.raises(ValueError, match="PROSPEO_API_KEY"):
        pipeline.run()


def test_live_prospeo_401_is_handled_without_crashing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.prospeo.requests.post",
        lambda *args, **kwargs: FakeResponse(401, {"error": True, "error_code": "INVALID_API_KEY"}),
    )

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.contacts_found == 0
    assert summary.companies_failed == 3
    assert summary.prospeo_status["status"] == "failed"
    assert any("401" in error["error"] for error in summary.prospeo_errors)


def test_live_prospeo_429_is_retried_and_reported(tmp_path, monkeypatch) -> None:
    attempts = {"count": 0}

    def fake_post(*args, **kwargs):
        attempts["count"] += 1
        return FakeResponse(429, {"error": True, "error_code": "RATE_LIMITED"}, headers={"Retry-After": "0"})

    monkeypatch.setattr("app.services.prospeo.requests.post", fake_post)

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.contacts_found == 0
    assert summary.prospeo_status["status"] == "failed"
    assert summary.companies_failed == 3
    assert attempts["count"] == 9


def test_live_prospeo_malformed_response_is_handled(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.prospeo.requests.post",
        lambda *args, **kwargs: FakeResponse(200, {"results": "bad-payload"}),
    )

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.contacts_found == 0
    assert summary.companies_failed == 3
    assert summary.prospeo_status["status"] == "failed"


def test_live_prospeo_empty_contacts_do_not_crash_pipeline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.prospeo.requests.post",
        lambda *args, **kwargs: FakeResponse(
            200,
            {"error": False, "results": [], "pagination": {"current_page": 1, "total_page": 1}},
        ),
    )

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.contacts_found == 0
    assert summary.companies_failed == 0
    assert summary.prospeo_status["status"] == "partial_success"


def test_live_prospeo_successful_contacts_without_emails(tmp_path, monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        if args[0] == PROSPEO_SEARCH_PERSON_URL:
            company_domain = extract_company_domain(kwargs)
            return FakeResponse(200, build_search_payload(company_domain, "Taylor Noemail"))
        return FakeResponse(200, build_enrich_payload(None))

    monkeypatch.setattr("app.services.prospeo.requests.post", fake_post)

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.contacts_found == 3
    assert summary.prospeo_emails_found == 0
    assert summary.contacts_without_email == 3


def test_live_prospeo_limit_contacts_respected(tmp_path, monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        if args[0] == PROSPEO_SEARCH_PERSON_URL:
            company_domain = extract_company_domain(kwargs)
            return FakeResponse(
                200,
                {
                    "error": False,
                    "results": [
                        build_search_payload(company_domain, "One Person")["results"][0],
                        build_search_payload(company_domain, "Two Person")["results"][0],
                    ],
                    "pagination": {"current_page": 1, "total_page": 1},
                },
            )
        return FakeResponse(200, build_enrich_payload("person@example.com"))

    monkeypatch.setattr("app.services.prospeo.requests.post", fake_post)
    pipeline = build_live_prospeo_pipeline(tmp_path, monkeypatch)
    pipeline.limit_contacts = 2
    summary = pipeline.run()

    assert summary.contacts_found == 2


def test_one_company_failure_does_not_crash_live_prospeo_pipeline(tmp_path, monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        if args[0] == PROSPEO_SEARCH_PERSON_URL:
            company_domain = extract_company_domain(kwargs)
            if company_domain == "anthropic.com":
                return FakeResponse(500, {"error": True, "error_code": "INTERNAL_ERROR"})
            return FakeResponse(200, build_search_payload(company_domain, "Jordan Lee"))
        return FakeResponse(200, build_enrich_payload("jordan.lee@example.com"))

    monkeypatch.setattr("app.services.prospeo.requests.post", fake_post)

    summary = build_live_prospeo_pipeline(tmp_path, monkeypatch).run()

    assert summary.contacts_found == 2
    assert summary.prospeo_emails_found == 2
    assert summary.companies_with_contacts == 2
    assert summary.companies_failed == 1
    assert summary.prospeo_status["status"] == "partial_success"
