"""Shared data models for the outreach pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Company:
    """A lookalike company returned from the Ocean stage."""

    name: str
    domain: str
    similarity_reason: str
    industry: str | None = None
    description: str | None = None


@dataclass
class Contact:
    """A decision-maker contact candidate."""

    name: str
    title: str
    company_name: str
    company_domain: str
    linkedin_url: str | None
    email: str | None = None
    verification_status: str = "unresolved"
    source_provider: str = "prospeo"
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifiedContact:
    """A contact after email resolution."""

    name: str
    title: str
    company_name: str
    company_domain: str
    linkedin_url: str | None
    email: str | None
    verification_status: str
    source_provider: str = "prospeo"
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailMessage:
    """An outbound outreach message."""

    contact_name: str
    company_domain: str
    recipient_email: str
    subject: str
    body: str


@dataclass
class EmailSendResult:
    """The result of a mock or live send attempt."""

    contact_name: str
    email: str
    company_domain: str
    send_status: str
    provider: str
    provider_message_id: str
    failure_reason: str | None = None


@dataclass
class StageStatus:
    """Status and counts for one pipeline stage."""

    status: str
    count_in: int
    count_out: int
    error_message: str | None = None


@dataclass
class PipelineRunSummary:
    """Audit summary for one pipeline run."""

    seed_domain: str
    started_at: str
    finished_at: str
    mock_mode: bool
    dry_run: bool
    companies_found: int
    contacts_found: int
    verified_emails: int
    unresolved_contacts: int
    duplicates_removed: int
    emails_ready: int
    emails_sent: int
    emails_failed: int
    pipeline_version: str = "ocean_prospeo_brevo"
    eazyreach_required: bool = False
    companies_queried: int = 0
    duplicate_contacts_removed: int = 0
    duplicate_emails_removed: int = 0
    emails_ready_for_brevo: int = 0
    prospeo_contacts_found: int = 0
    prospeo_emails_found: int = 0
    contacts_without_email: int = 0
    send_live: bool = False
    blocked_unverified_count: int = 0
    ocean_source: str = "mock"
    prospeo_mode: str = "mock"
    eazyreach_mode: str = "mock/fallback"
    brevo_mode: str = "mock"
    companies_with_contacts: int = 0
    companies_failed: int = 0
    prospeo_errors: list[dict[str, Any]] = field(default_factory=list)
    mock_verified_count: int = 0
    send_decision: str = "not_applicable"
    stage_statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    ocean_status: dict[str, Any] = field(default_factory=dict)
    prospeo_status: dict[str, Any] = field(default_factory=dict)
    eazyreach_status: dict[str, Any] = field(default_factory=dict)
    brevo_status: dict[str, Any] = field(default_factory=dict)
    failed_contacts: list[dict[str, Any]] = field(default_factory=list)
    send_results: list[dict[str, Any]] = field(default_factory=list)
