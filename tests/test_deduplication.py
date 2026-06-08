from app.models import VerifiedContact
from app.pipeline import OutreachPipeline


def test_duplicate_emails_are_removed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="notion.so",
        service_modes={"ocean": "mock", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
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
    contacts = [
        VerifiedContact(
            name="Ava Patel",
            title="Founder",
            company_name="Airtable",
            company_domain="airtable.com",
            linkedin_url="https://linkedin.com/in/ava",
            email="AVA@AIRTABLE.COM",
            verification_status="verified",
        ),
        VerifiedContact(
            name="Mia Johnson",
            title="CTO",
            company_name="Airtable",
            company_domain="airtable.com",
            linkedin_url="https://linkedin.com/in/mia",
            email="ava@airtable.com",
            verification_status="verified",
        ),
    ]

    unique_contacts, duplicates_removed = pipeline._deduplicate_contacts(contacts)

    assert len(unique_contacts) == 1
    assert duplicates_removed == 1
