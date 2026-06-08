from app.email_templates import build_outreach_email
from app.models import VerifiedContact


def test_email_template_contains_expected_content() -> None:
    contact = VerifiedContact(
        name="Ava Patel",
        title="Founder",
        company_name="Airtable",
        company_domain="airtable.com",
        linkedin_url="https://linkedin.com/in/ava",
        email="ava@airtable.com",
        verification_status="verified",
    )

    message = build_outreach_email(contact, mock_mode=True)

    assert "Airtable" in message.subject
    assert "Ava Patel" in message.body
    assert message.recipient_email == "ava@airtable.com"
