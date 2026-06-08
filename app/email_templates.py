"""Email template helpers."""

from __future__ import annotations

from app.models import EmailMessage, VerifiedContact


def build_outreach_email(contact: VerifiedContact, mock_mode: bool) -> EmailMessage:
    """Create a simple outreach email for a verified contact."""
    mode_label = "Mock" if mock_mode else "Live"
    subject = f"{mode_label} outreach idea for {contact.company_name}"
    body = (
        f"Hi {contact.name},\n\n"
        f"I noticed {contact.company_name} while researching companies similar to {contact.company_domain}.\n"
        "This message is generated from the VocalLabs outreach pipeline demo flow.\n\n"
        "Best,\n"
        "VocalLabs Outreach"
    )
    return EmailMessage(
        contact_name=contact.name,
        company_domain=contact.company_domain,
        recipient_email=contact.email or "",
        subject=subject,
        body=body,
    )
