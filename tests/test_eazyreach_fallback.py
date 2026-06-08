from app.models import Contact, VerifiedContact
from app.pipeline import OutreachPipeline
from app.services.eazyreach import EazyreachService


def test_mock_eazyreach_returns_mock_verified_and_unresolved() -> None:
    service = EazyreachService(mode="mock", simulate_failures=False)
    contacts = [
        Contact(
            name="Sarah Chen",
            title="VP Growth",
            company_name="Airtable",
            company_domain="airtable.com",
            linkedin_url="https://linkedin.com/in/sarah-chen",
        ),
        Contact(
            name="Jordan Lee",
            title="CTO",
            company_name="ClickUp",
            company_domain="clickup.com",
            linkedin_url="https://linkedin.com/in/jordan-lee",
        ),
    ]

    resolved = service.resolve_emails(contacts)

    assert resolved[0].verification_status == "unresolved"
    assert resolved[1].verification_status == "mock_verified"
    assert resolved[1].email == "jordan@clickup.com"
    assert resolved[1].metadata["resolver_mode"] == "mock/fallback"


def test_live_brevo_filters_out_mock_verified_emails_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="notion.so",
        service_modes={"ocean": "mock", "prospeo": "mock", "eazyreach": "mock", "brevo": "live"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=False,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )
    contacts = [
        VerifiedContact(
            name="Ava Patel",
            title="Founder",
            company_name="Airtable",
            company_domain="airtable.com",
            linkedin_url="https://linkedin.com/in/ava",
            email="ava@airtable.com",
            verification_status="mock_verified",
        ),
        VerifiedContact(
            name="Mia Johnson",
            title="CTO",
            company_name="Airtable",
            company_domain="airtable.com",
            linkedin_url="https://linkedin.com/in/mia",
            email="mia@airtable.com",
            verification_status="verified",
        ),
    ]

    filtered = pipeline._filter_sendable_contacts(contacts)

    assert len(filtered) == 1
    assert filtered[0].verification_status == "verified"


def test_live_brevo_can_include_mock_verified_when_explicitly_allowed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="notion.so",
        service_modes={"ocean": "mock", "prospeo": "mock", "eazyreach": "mock", "brevo": "live"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=False,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=True,
        send_live=False,
    )
    contacts = [
        VerifiedContact(
            name="Ava Patel",
            title="Founder",
            company_name="Airtable",
            company_domain="airtable.com",
            linkedin_url="https://linkedin.com/in/ava",
            email="ava@airtable.com",
            verification_status="mock_verified",
        )
    ]

    filtered = pipeline._filter_sendable_contacts(contacts)

    assert len(filtered) == 1
    assert filtered[0].verification_status == "mock_verified"
