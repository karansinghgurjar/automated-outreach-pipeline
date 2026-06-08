"""Pipeline orchestration module."""

from __future__ import annotations

from csv import DictWriter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from app.config import Settings, get_settings
from app.email_templates import build_outreach_email
from app.models import (
    Company,
    Contact,
    EmailMessage,
    EmailSendResult,
    PipelineRunSummary,
    StageStatus,
    VerifiedContact,
)
from app.services.brevo import BrevoService
from app.services.eazyreach import EazyreachService
from app.services.ocean import OceanService
from app.services.prospeo import ProspeoService
from app.utils.logger import configure_logger
from app.utils.validators import (
    ensure_positive_limit,
    ensure_positive_timeout,
    normalize_domain,
    normalize_email,
    validate_domain,
)


class OutreachPipeline:
    """Coordinates the high-level outreach flow."""

    def __init__(
        self,
        seed_domain: str,
        service_modes: dict[str, str],
        limit_companies: int,
        limit_contacts: int,
        max_contacts_per_company: int,
        dry_run: bool,
        simulate_failures: bool,
        timeout_seconds: float,
        max_retries: int,
        output_dir: str,
        assume_yes: bool,
        allow_unverified_live_send: bool,
        send_live: bool,
    ) -> None:
        self.settings: Settings = get_settings()
        self.seed_domain = validate_domain(seed_domain)
        self.service_modes = service_modes
        self.mock_mode = all(mode in {"mock", "skipped"} for mode in service_modes.values())
        self.ocean_source = self._resolve_ocean_source()
        self.limit_companies = ensure_positive_limit(limit_companies, "limit-companies")
        self.limit_contacts = ensure_positive_limit(limit_contacts, "limit-contacts")
        self.max_contacts_per_company = ensure_positive_limit(
            max_contacts_per_company,
            "max-contacts-per-company",
        )
        self.dry_run = dry_run
        self.simulate_failures = simulate_failures
        self.timeout_seconds = ensure_positive_timeout(timeout_seconds)
        self.max_retries = ensure_positive_limit(max_retries, "max-retries")
        self.assume_yes = assume_yes
        self.allow_unverified_live_send = allow_unverified_live_send
        self.send_live = send_live

        self.output_root = Path(output_dir)
        self.runs_dir = self.output_root / "runs"
        self.logs_dir = self.output_root / "logs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.log_path = self.logs_dir / f"{self.timestamp}_pipeline.log"
        self.logger = configure_logger("vocallabs.pipeline", self.log_path, self.settings.log_level)

        self.ocean = OceanService(mode=self.service_modes["ocean"])
        self.prospeo = ProspeoService(
            mode=self.service_modes["prospeo"],
            max_contacts_per_company=self.max_contacts_per_company,
            simulate_failures=self.simulate_failures,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
        )
        self.eazyreach = EazyreachService(
            mode=self.service_modes["eazyreach"],
            simulate_failures=self.simulate_failures,
        )
        self.brevo = BrevoService(
            mode=self.service_modes["brevo"],
            sender_email=self.settings.brevo_sender_email,
            sender_name=self.settings.brevo_sender_name,
            api_key=self.settings.brevo_api_key,
            simulate_failures=self.simulate_failures,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
        )

    def run(self) -> PipelineRunSummary:
        """Run the pipeline end to end."""
        started_at = datetime.now().isoformat(timespec="seconds")
        self._preflight_live_modes()
        self._print_run_header()
        self.logger.info(
            "Pipeline started for seed_domain=%s service_modes=%s",
            self.seed_domain,
            self.service_modes,
        )

        companies, ocean_status = self._run_company_stage()
        companies, company_duplicates_removed = self._deduplicate_companies(companies)
        contacts, prospeo_status = self._run_contact_stage(companies)
        raw_contacts = list(contacts)
        contacts, contact_duplicates_removed = self._deduplicate_contacts_by_identity(contacts)
        verified_contacts, eazyreach_status = self._run_email_stage(contacts)
        unique_verified_contacts, duplicate_emails_removed = self._deduplicate_contacts(verified_contacts)
        duplicates_removed = company_duplicates_removed + contact_duplicates_removed + duplicate_emails_removed

        ready_contacts = [contact for contact in unique_verified_contacts if contact.email]
        sendable_contacts = self._filter_sendable_contacts(ready_contacts)
        unresolved_contacts = [contact for contact in verified_contacts if not contact.email]
        email_messages = [
            build_outreach_email(contact, self.service_modes["brevo"] == "mock")
            for contact in ready_contacts
        ]

        blocked_live_send_count = len(ready_contacts) - len(sendable_contacts)
        if blocked_live_send_count:
            self._print_warning(
                f"{blocked_live_send_count} fallback email(s) are excluded from live sending by default."
            )
            self.logger.warning(
                "Blocked %s fallback email(s) from live sending because allow_unverified_live_send is disabled.",
                blocked_live_send_count,
            )
        if (
            self.send_live
            and not self.dry_run
            and self.service_modes["brevo"] == "live"
            and ready_contacts
            and not sendable_contacts
        ):
            self._print_warning("Live sending blocked because emails are not verified by a live resolver.")
            self.logger.warning(
                "Live sending blocked because all resolved emails are fallback-only and not provider-verified."
            )

        proceed_with_send = self._handle_safety_checkpoint(
            companies_found=len(companies),
            contacts_found=len(contacts),
            verified_contacts=sendable_contacts,
            duplicates_removed=duplicates_removed,
            email_messages=email_messages,
        )
        send_decision = self._determine_send_decision(
            proceed_with_send=proceed_with_send,
            eligible_live_recipients=len(sendable_contacts),
        )
        send_results, brevo_status = self._run_send_stage(
            verified_contacts=sendable_contacts if not self.dry_run else ready_contacts,
            email_messages=email_messages,
            proceed_with_send=proceed_with_send,
            send_decision=send_decision,
        )

        finished_at = datetime.now().isoformat(timespec="seconds")
        stage_statuses = {
            "ocean": asdict(ocean_status),
            "prospeo": asdict(prospeo_status),
            "eazyreach": asdict(eazyreach_status),
            "brevo": asdict(brevo_status),
        }
        summary = self._build_summary(
            started_at=started_at,
            finished_at=finished_at,
            companies=companies,
            contacts=contacts,
            raw_contacts=raw_contacts,
            verified_contacts=sendable_contacts,
            all_resolved_contacts=ready_contacts,
            unresolved_contacts=unresolved_contacts,
            duplicates_removed=duplicates_removed,
            send_results=send_results,
            send_decision=send_decision,
            stage_statuses=stage_statuses,
            blocked_unverified_count=blocked_live_send_count,
            duplicate_emails_removed=duplicate_emails_removed,
            duplicate_contacts_removed=contact_duplicates_removed,
        )
        json_path, csv_path = self._write_reports(
            summary,
            all_verified_contacts=verified_contacts,
            email_messages=email_messages,
            send_results=send_results,
        )

        self.logger.info("Run completed. JSON summary saved: %s", json_path.resolve())
        self.logger.info("CSV report saved: %s", csv_path.resolve())
        self.logger.info("Log saved: %s", self.log_path.resolve())

        print("")
        print("Pipeline completed")
        print("------------------")
        print(f"Companies found: {summary.companies_found}")
        print(f"Contacts found: {summary.contacts_found}")
        print(f"Emails found: {summary.prospeo_emails_found}")
        print(f"Contacts without email: {summary.contacts_without_email}")
        print(f"Duplicate contacts removed: {summary.duplicate_contacts_removed}")
        print(f"Duplicate emails removed: {summary.duplicate_emails_removed}")
        print(f"Emails ready: {summary.emails_ready_for_brevo}")
        print(f"Emails sent: {summary.emails_sent}")
        print(f"Emails failed: {summary.emails_failed}")
        print(f"JSON summary: {json_path.resolve()}")
        print(f"CSV contacts: {csv_path.resolve()}")
        print(f"Log file: {self.log_path.resolve()}")
        return summary

    def _run_company_stage(self) -> tuple[list[Company], StageStatus]:
        self._print_stage_header(1, 4, "Ocean.io", self.service_modes["ocean"])
        self.logger.info("Starting Ocean stage.")
        try:
            companies = self.ocean.find_lookalike_companies(self.seed_domain, self.limit_companies)
            status_name = "success" if companies else "partial_success"
            status = StageStatus(
                status=status_name,
                count_in=1,
                count_out=len(companies),
            )
            if not companies:
                self._print_warning("Ocean returned no companies.")
            self.logger.info("Ocean stage complete with %s companies.", len(companies))
            print(f"Companies found: {len(companies)}")
            return companies, status
        except Exception as exc:
            self.logger.exception("Ocean stage failed.")
            status = StageStatus(
                status="failed",
                count_in=1,
                count_out=0,
                error_message=str(exc),
            )
            print("Companies found: 0")
            return [], status

    def _run_contact_stage(self, companies: list[Company]) -> tuple[list[Contact], StageStatus]:
        self._print_stage_header(2, 4, "Prospeo", self.service_modes["prospeo"])
        self.logger.info("Starting Prospeo stage.")
        try:
            company_domains = [company.domain for company in companies]
            contacts = self.prospeo.find_decision_makers(companies, self.limit_contacts)
            prospeo_stats = getattr(self.prospeo, "last_run_stats", {})
            companies_failed = int(prospeo_stats.get("companies_failed", 0) or 0)
            status_name = "success"
            if companies_failed:
                if companies_failed == len(company_domains) and not contacts:
                    status_name = "failed"
                else:
                    status_name = "partial_success"
            elif companies and len({contact.company_domain for contact in contacts}) < len(company_domains):
                status_name = "partial_success"
            if not contacts:
                if status_name != "failed":
                    status_name = "partial_success" if companies else "success"
                self._print_warning("Prospeo returned no contacts.")
            errors = prospeo_stats.get("errors", [])
            if isinstance(errors, list):
                for error in errors:
                    if not isinstance(error, dict):
                        continue
                    company_domain = error.get("company_domain", "unknown")
                    error_message = error.get("error", "Unknown Prospeo error")
                    self.logger.warning(
                        "Prospeo lookup failed for %s (%s)",
                        company_domain,
                        error_message,
                    )
            status = StageStatus(
                status=status_name,
                count_in=len(company_domains),
                count_out=len(contacts),
            )
            self.logger.info(
                "Prospeo stage complete with %s contacts, %s emails, %s contacts without email, %s companies failed.",
                len(contacts),
                sum(1 for contact in contacts if contact.email),
                sum(1 for contact in contacts if not contact.email),
                companies_failed,
            )
            print(f"Contacts found: {len(contacts)}")
            print(f"Emails found: {sum(1 for contact in contacts if contact.email)}")
            print(f"Contacts without email: {sum(1 for contact in contacts if not contact.email)}")
            print(f"Companies failed: {companies_failed}")
            return contacts, status
        except Exception as exc:
            self.logger.exception("Prospeo stage failed.")
            status = StageStatus(
                status="failed",
                count_in=len(companies),
                count_out=0,
                error_message=str(exc),
            )
            print("Contacts found: 0")
            print("Emails found: 0")
            print("Contacts without email: 0")
            print(f"Companies failed: {len(companies)}")
            return [], status

    def _run_email_stage(self, contacts: list[Contact]) -> tuple[list[VerifiedContact], StageStatus]:
        if self.service_modes["eazyreach"] == "skipped":
            self._print_stage_header(3, 4, "Eazyreach", "skipped")
            self.logger.info("Skipping Eazyreach stage and using Prospeo email data directly.")
            for contact in contacts:
                if not contact.email:
                    self.logger.info("Contact skipped because no email: %s at %s", contact.name, contact.company_domain)
            converted_contacts = [self._contact_to_verified_contact(contact) for contact in contacts]
            unresolved_count = sum(1 for contact in converted_contacts if not contact.email)
            print(f"Resolved contacts: {len(converted_contacts)}")
            print(f"Unresolved contacts: {unresolved_count}")
            return (
                converted_contacts,
                StageStatus(
                    status="skipped",
                    count_in=len(contacts),
                    count_out=len(converted_contacts),
                    error_message=None,
                ),
            )

        self._print_stage_header(3, 4, "Eazyreach", self.service_modes["eazyreach"])
        self.logger.info("Starting Eazyreach stage.")
        try:
            verified_contacts = self.eazyreach.resolve_emails(contacts)
            unresolved_count = sum(
                1 for contact in verified_contacts if contact.verification_status == "unresolved"
            )
            for contact in verified_contacts:
                if contact.verification_status == "unresolved":
                    self.logger.warning(
                        "Unresolved contact: %s at %s (%s)",
                        contact.name,
                        contact.company_domain,
                        contact.failure_reason,
                    )
            status_name = "partial_success" if unresolved_count else "success"
            status = StageStatus(
                status=status_name,
                count_in=len(contacts),
                count_out=len(verified_contacts),
            )
            if verified_contacts and unresolved_count == len(verified_contacts):
                self._print_warning("Eazyreach returned no resolvable emails.")
            self.logger.info(
                "Eazyreach stage complete with %s resolved and %s unresolved contacts.",
                len(verified_contacts) - unresolved_count,
                unresolved_count,
            )
            print(f"Resolved contacts: {len(verified_contacts)}")
            print(f"Unresolved contacts: {unresolved_count}")
            return verified_contacts, status
        except Exception as exc:
            self.logger.exception("Eazyreach stage failed.")
            status = StageStatus(
                status="failed",
                count_in=len(contacts),
                count_out=0,
                error_message=str(exc),
            )
            print("Resolved contacts: 0")
            print("Unresolved contacts: 0")
            return [], status

    def _run_send_stage(
        self,
        verified_contacts: list[VerifiedContact],
        email_messages: list[EmailMessage],
        proceed_with_send: bool,
        send_decision: str,
    ) -> tuple[list[EmailSendResult], StageStatus]:
        self._print_stage_header(4, 4, "Brevo", self.service_modes["brevo"])
        self.logger.info("Starting Brevo stage.")
        try:
            if send_decision == "live_send_not_enabled":
                status = StageStatus(
                    status="skipped",
                    count_in=len(verified_contacts),
                    count_out=0,
                    error_message=None,
                )
                self.logger.info("Brevo live mode selected but --send-live was not provided.")
                print("Emails processed: 0")
                return [], status
            if send_decision == "blocked_unverified":
                status = StageStatus(
                    status="blocked",
                    count_in=len(verified_contacts),
                    count_out=0,
                    error_message="Live sending blocked because emails are not verified by a live resolver.",
                )
                self.logger.info("Brevo live send blocked because no provider-verified recipients were available.")
                print("Emails processed: 0")
                return [], status
            if send_decision == "cancelled":
                cancelled_results = [
                    EmailSendResult(
                        contact_name=contact.name,
                        email=contact.email or "",
                        company_domain=contact.company_domain,
                        send_status="cancelled",
                        provider="brevo",
                        provider_message_id="",
                        failure_reason="User rejected the safety checkpoint",
                    )
                    for contact in verified_contacts
                ]
                status = StageStatus(
                    status="cancelled",
                    count_in=len(verified_contacts),
                    count_out=0,
                    error_message=None,
                )
                self._print_warning("User rejected the safety checkpoint. No emails were sent.")
                self.logger.info("Brevo stage cancelled by user before sending.")
                print("Emails processed: 0")
                return cancelled_results, status

            send_results = self.brevo.send_outreach(
                verified_contacts=verified_contacts,
                email_messages=email_messages,
                dry_run=self.dry_run or not proceed_with_send,
            )
            failure_count = sum(1 for result in send_results if result.send_status == "failed")
            for result in send_results:
                if result.send_status == "failed":
                    self.logger.error(
                        "Send failed for %s at %s (%s)",
                        result.contact_name,
                        result.company_domain,
                        result.failure_reason,
                    )
            status_name = "success"
            if failure_count:
                status_name = "partial_success"
            status = StageStatus(
                status=status_name,
                count_in=len(verified_contacts),
                count_out=len(send_results),
                error_message=None,
            )
            self.logger.info("Brevo stage complete with %s results.", len(send_results))
            print(f"Emails processed: {len(send_results)}")
            return send_results, status
        except Exception as exc:
            self.logger.exception("Brevo stage failed.")
            status = StageStatus(
                status="failed",
                count_in=len(verified_contacts),
                count_out=0,
                error_message=str(exc),
            )
            print("Emails processed: 0")
            return [], status

    def _deduplicate_contacts(
        self,
        verified_contacts: list[VerifiedContact],
    ) -> tuple[list[VerifiedContact], int]:
        unique_contacts: list[VerifiedContact] = []
        seen_emails: set[str] = set()
        duplicates_removed = 0

        for contact in verified_contacts:
            normalized = normalize_email(contact.email)
            if not normalized:
                unique_contacts.append(contact)
                continue
            if normalized in seen_emails:
                duplicates_removed += 1
                self.logger.info("Duplicate emails skipped: %s", normalized)
                continue
            seen_emails.add(normalized)
            unique_contacts.append(contact)

        return unique_contacts, duplicates_removed

    def _deduplicate_companies(self, companies: list[Company]) -> tuple[list[Company], int]:
        unique_companies: list[Company] = []
        seen_domains: set[str] = set()
        duplicates_removed = 0

        for company in companies:
            normalized_domain = normalize_domain(company.domain)
            if normalized_domain in seen_domains:
                duplicates_removed += 1
                self.logger.info("Duplicate company removed: %s", normalized_domain)
                continue
            seen_domains.add(normalized_domain)
            company.domain = normalized_domain
            unique_companies.append(company)

        return unique_companies, duplicates_removed

    def _deduplicate_contacts_by_identity(
        self,
        contacts: list[Contact],
    ) -> tuple[list[Contact], int]:
        unique_contacts: list[Contact] = []
        seen_keys: set[tuple[str, ...]] = set()
        duplicates_removed = 0

        for contact in contacts:
            linkedin_key = (contact.linkedin_url or "").strip().lower()
            if linkedin_key:
                key = ("linkedin", linkedin_key)
            else:
                key = (
                    "identity",
                    contact.company_domain.lower(),
                    contact.name.strip().lower(),
                )
            if key in seen_keys:
                duplicates_removed += 1
                self.logger.info("Duplicate contact removed: %s at %s", contact.name, contact.company_domain)
                continue
            seen_keys.add(key)
            unique_contacts.append(contact)

        return unique_contacts, duplicates_removed

    def _contact_to_verified_contact(self, contact: Contact) -> VerifiedContact:
        verification_status = contact.verification_status if contact.email else "unresolved"
        return VerifiedContact(
            name=contact.name,
            title=contact.title,
            company_name=contact.company_name,
            company_domain=contact.company_domain,
            linkedin_url=contact.linkedin_url,
            email=contact.email,
            verification_status=verification_status,
            source_provider=contact.source_provider,
            failure_reason=contact.failure_reason if not contact.email else None,
            metadata={**contact.metadata, "resolver_mode": "skipped"},
        )

    def _handle_safety_checkpoint(
        self,
        companies_found: int,
        contacts_found: int,
        verified_contacts: list[VerifiedContact],
        duplicates_removed: int,
        email_messages: list[EmailMessage],
    ) -> bool:
        if self.dry_run:
            return False
        if self.service_modes["brevo"] == "live" and not self.send_live:
            self.logger.info("Live sending not enabled because --send-live was not provided.")
            return False
        if not verified_contacts:
            self.logger.info("No live-send-eligible contacts available at safety checkpoint.")
            self._print_warning("No live-send-eligible emails are available for sending.")
            return False
        if self.assume_yes and self.service_modes["brevo"] == "mock":
            self.logger.info("Auto-confirm enabled for mock mode.")
            return True

        print("")
        print("## Safety Checkpoint")
        print("")
        print(f"Seed domain: {self.seed_domain}")
        print(f"Source mode: {self.ocean_source}")
        print(f"Prospeo mode: {self.service_modes['prospeo']}")
        print(f"Eazyreach mode: {self._resolve_eazyreach_mode()}")
        print(f"Companies found: {companies_found}")
        print(f"Contacts found: {contacts_found}")
        print(f"Recipient count: {len(verified_contacts)}")
        print(f"Duplicates removed: {duplicates_removed}")
        print("")

        subject_by_email = {message.recipient_email.lower(): message.subject for message in email_messages}
        for index, contact in enumerate(verified_contacts[:10], start=1):
            subject = subject_by_email.get((contact.email or "").lower(), "")
            print(
                f"{index}. {contact.name} | {contact.title} | {contact.email} | "
                f"{contact.company_domain} | {subject}"
            )

        response = input("Continue sending live emails? [y/N]: ").strip().lower()
        # This checkpoint intentionally defaults to no to prevent accidental bulk sends.
        if response != "y":
            self.logger.info("User declined send at safety checkpoint.")
            return False

        self.logger.info("User approved send at safety checkpoint.")
        return True

    def _build_summary(
        self,
        started_at: str,
        finished_at: str,
        companies: list[Company],
        contacts: list[Contact],
        raw_contacts: list[Contact],
        verified_contacts: list[VerifiedContact],
        all_resolved_contacts: list[VerifiedContact],
        unresolved_contacts: list[VerifiedContact],
        duplicates_removed: int,
        send_results: list[EmailSendResult],
        send_decision: str,
        stage_statuses: dict[str, dict],
        blocked_unverified_count: int,
        duplicate_emails_removed: int,
        duplicate_contacts_removed: int,
    ) -> PipelineRunSummary:
        emails_sent = sum(1 for result in send_results if result.send_status in {"mock_sent", "sent"})
        emails_failed = sum(1 for result in send_results if result.send_status == "failed")

        failed_contacts = [
            {
                "contact_name": contact.name,
                "company_domain": contact.company_domain,
                "failure_reason": contact.failure_reason,
            }
            for contact in unresolved_contacts
        ]
        prospeo_stats = getattr(self.prospeo, "last_run_stats", {})
        prospeo_errors = prospeo_stats.get("errors", [])
        verified_count = sum(1 for contact in all_resolved_contacts if contact.verification_status == "verified")
        mock_verified_count = sum(
            1 for contact in all_resolved_contacts if contact.verification_status == "mock_verified"
        )
        contacts_without_email = sum(1 for contact in raw_contacts if not contact.email)

        return PipelineRunSummary(
            seed_domain=self.seed_domain,
            started_at=started_at,
            finished_at=finished_at,
            mock_mode=self.mock_mode,
            dry_run=self.dry_run,
            companies_found=len(companies),
            companies_queried=len(companies),
            contacts_found=len(raw_contacts),
            verified_emails=verified_count,
            unresolved_contacts=len(unresolved_contacts),
            duplicates_removed=duplicates_removed,
            duplicate_contacts_removed=duplicate_contacts_removed,
            duplicate_emails_removed=duplicate_emails_removed,
            emails_ready=len(verified_contacts),
            emails_ready_for_brevo=len(verified_contacts),
            emails_sent=emails_sent,
            emails_failed=emails_failed,
            prospeo_contacts_found=len(raw_contacts),
            prospeo_emails_found=sum(1 for contact in raw_contacts if contact.email),
            contacts_without_email=contacts_without_email,
            send_live=self.send_live and not self.dry_run,
            blocked_unverified_count=blocked_unverified_count,
            ocean_source=self.ocean_source,
            prospeo_mode=self.service_modes["prospeo"],
            eazyreach_mode=self._resolve_eazyreach_mode(),
            brevo_mode=self.service_modes["brevo"],
            companies_with_contacts=int(prospeo_stats.get("companies_with_contacts", 0) or 0),
            companies_failed=int(prospeo_stats.get("companies_failed", 0) or 0),
            prospeo_errors=prospeo_errors if isinstance(prospeo_errors, list) else [],
            mock_verified_count=mock_verified_count,
            send_decision=send_decision,
            stage_statuses=stage_statuses,
            ocean_status=stage_statuses["ocean"],
            prospeo_status=stage_statuses["prospeo"],
            eazyreach_status=stage_statuses["eazyreach"],
            brevo_status=stage_statuses["brevo"],
            failed_contacts=failed_contacts,
            send_results=[asdict(result) for result in send_results],
        )

    def _write_reports(
        self,
        summary: PipelineRunSummary,
        all_verified_contacts: list[VerifiedContact],
        email_messages: list[EmailMessage],
        send_results: list[EmailSendResult],
    ) -> tuple[Path, Path]:
        json_path = self.runs_dir / f"{self.timestamp}_summary.json"
        csv_path = self.runs_dir / f"{self.timestamp}_contacts.csv"

        json_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")

        message_by_email = {message.recipient_email: message for message in email_messages}
        result_by_email = {result.email: result for result in send_results}

        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = DictWriter(
                csv_file,
                fieldnames=[
                    "company_domain",
                    "contact_name",
                    "title",
                    "linkedin_url",
                    "email",
                    "source_provider",
                    "email_status",
                    "send_status",
                    "provider_message_id",
                    "failure_reason",
                ],
            )
            writer.writeheader()

            for contact in all_verified_contacts:
                message = message_by_email.get(contact.email or "")
                result = result_by_email.get(contact.email or "")
                writer.writerow(
                    {
                        "company_domain": contact.company_domain,
                        "contact_name": contact.name,
                        "title": contact.title,
                        "linkedin_url": contact.linkedin_url or "",
                        "email": contact.email or "",
                        "source_provider": contact.source_provider,
                        "email_status": contact.verification_status,
                        "send_status": result.send_status if result else "",
                        "provider_message_id": result.provider_message_id if result else "",
                        "failure_reason": (result.failure_reason if result else "") or contact.failure_reason or "",
                    }
                )

        return json_path, csv_path

    def _preflight_live_modes(self) -> None:
        selected_live_modes = [name for name, mode in self.service_modes.items() if mode == "live"]
        if not selected_live_modes:
            return

        if "brevo" in selected_live_modes and self.send_live and not self.dry_run:
            missing = []
            if not self.settings.brevo_api_key:
                missing.append("BREVO_API_KEY")
            if not self.settings.brevo_sender_email:
                missing.append("BREVO_SENDER_EMAIL")
            if not self.settings.brevo_sender_name:
                missing.append("BREVO_SENDER_NAME")
            if missing:
                raise ValueError(
                    f"Missing Brevo environment variables for live mode: {', '.join(missing)}."
                )

        if "prospeo" in selected_live_modes and not self.settings.prospeo_api_key:
            raise ValueError("PROSPEO_API_KEY is required for live Prospeo mode.")

        unsupported_live = [name for name in selected_live_modes if name not in {"brevo", "prospeo"}]
        if unsupported_live:
            raise NotImplementedError(
                f"Live mode is not implemented yet for: {', '.join(sorted(unsupported_live))}."
            )

    def _print_run_header(self) -> None:
        print("")
        print("====================================")
        print("Automated Outreach Pipeline")
        print("====================================")
        print(f"Seed domain: {self.seed_domain}")
        print(f"Ocean source: {self.ocean_source}")
        print(f"Ocean mode: {self.service_modes['ocean']}")
        print(f"Prospeo mode: {self.service_modes['prospeo']}")
        print(f"Eazyreach mode: {self._resolve_eazyreach_mode()}")
        print(f"Brevo mode: {self.service_modes['brevo']}")
        print(f"Limit companies: {self.limit_companies}")
        print(f"Limit contacts: {self.limit_contacts}")
        print(f"Max contacts/company: {self.max_contacts_per_company}")
        print(f"Timeout (seconds): {self.timeout_seconds}")
        print(f"Max retries: {self.max_retries}")
        print(f"Output directory: {self.output_root.resolve()}")
        print(f"Dry run: {self.dry_run}")
        print(f"Send live: {self.send_live}")
        print(f"Simulate failures: {self.simulate_failures}")
        print(f"Allow unverified live send: {self.allow_unverified_live_send}")
        if self.assume_yes and self.service_modes["brevo"] != "mock" and not self.dry_run:
            self._print_warning("--yes is ignored for live Brevo sending to preserve confirmation safety.")
        if self.allow_unverified_live_send and self.service_modes["brevo"] != "live":
            self._print_warning("--allow-unverified-live-send only matters when Brevo is in live mode.")

    def _print_stage_header(self, current: int, total: int, service_name: str, mode: str) -> None:
        print("")
        print(f"[{current}/{total}] {service_name} ({mode})")
        print("-" * 32)

    def _print_warning(self, message: str) -> None:
        print(f"Warning: {message}")

    def _determine_send_decision(
        self,
        proceed_with_send: bool,
        eligible_live_recipients: int,
    ) -> str:
        """Describe why the send stage ran or did not run."""
        if self.dry_run:
            return "dry_run"
        if self.service_modes["brevo"] == "live" and not self.send_live:
            return "live_send_not_enabled"
        if self.service_modes["brevo"] == "live" and eligible_live_recipients == 0:
            return "blocked_unverified"
        if proceed_with_send:
            return "confirmed_send"
        return "cancelled"

    def _resolve_ocean_source(self) -> str:
        """Return human-readable Ocean source info for summaries."""
        if self.service_modes["ocean"] == "live":
            return "live_placeholder"
        return self.service_modes["ocean"]

    def _resolve_eazyreach_mode(self) -> str:
        if self.service_modes["eazyreach"] == "live":
            return "live-placeholder"
        if self.service_modes["eazyreach"] == "mock":
            return "mock/fallback"
        return self.service_modes["eazyreach"]

    def _filter_sendable_contacts(
        self,
        contacts_with_email: list[VerifiedContact],
    ) -> list[VerifiedContact]:
        if self.service_modes["brevo"] != "live" or self.allow_unverified_live_send or self.dry_run:
            return contacts_with_email
        return [
            contact for contact in contacts_with_email if contact.verification_status == "verified"
        ]
