"""Brevo service layer."""

from __future__ import annotations

import requests

from app.config import get_settings
from app.models import EmailMessage, EmailSendResult, VerifiedContact
from app.utils.retry import RetryConfig, RetryableOperationError, run_with_retry


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_ACCOUNT_URL = "https://api.brevo.com/v3/account"


class BrevoService:
    """Handles outbound campaign sending via Brevo."""

    def __init__(
        self,
        mode: str = "mock",
        sender_email: str = "",
        sender_name: str = "",
        api_key: str = "",
        simulate_failures: bool = False,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.mode = mode
        self.sender_email = sender_email
        self.sender_name = sender_name
        self.api_key = api_key
        self.simulate_failures = simulate_failures
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.settings = get_settings()

    def send_outreach(
        self,
        verified_contacts: list[VerifiedContact],
        email_messages: list[EmailMessage],
        dry_run: bool = False,
    ) -> list[EmailSendResult]:
        """Send or simulate outbound outreach."""
        if self.mode == "mock":
            return self._send_mock_outreach(verified_contacts, email_messages, dry_run)
        if self.mode == "fake_http":
            return self._send_fake_http_outreach(verified_contacts, email_messages, dry_run)

        if not self.api_key:
            raise ValueError("BREVO_API_KEY is required for live Brevo sending.")
        if not self.sender_email:
            raise ValueError("BREVO_SENDER_EMAIL is required for live Brevo sending.")
        if not self.sender_name:
            raise ValueError("BREVO_SENDER_NAME is required for live Brevo sending.")

        return self._send_live_outreach(verified_contacts, email_messages, dry_run)

    def _send_mock_outreach(
        self,
        verified_contacts: list[VerifiedContact],
        email_messages: list[EmailMessage],
        dry_run: bool,
    ) -> list[EmailSendResult]:
        message_by_email = {
            message.recipient_email.lower(): message for message in email_messages
        }
        results: list[EmailSendResult] = []

        for index, contact in enumerate(verified_contacts):
            email = (contact.email or "").lower()
            if not email:
                continue

            _ = message_by_email[email]
            if self.simulate_failures and index == 0:
                results.append(
                    EmailSendResult(
                        contact_name=contact.name,
                        email=email,
                        company_domain=contact.company_domain,
                        send_status="failed",
                        provider="brevo",
                        provider_message_id=f"brevo-mock-failed-{contact.company_domain.replace('.', '-')}",
                        failure_reason="Simulated Brevo send failure",
                    )
                )
                continue

            results.append(
                EmailSendResult(
                    contact_name=contact.name,
                    email=email,
                    company_domain=contact.company_domain,
                    send_status="dry_run" if dry_run else "mock_sent",
                    provider="brevo",
                    provider_message_id=f"brevo-mock-{contact.company_domain.replace('.', '-')}",
                )
            )

        return results

    def _send_fake_http_outreach(
        self,
        verified_contacts: list[VerifiedContact],
        email_messages: list[EmailMessage],
        dry_run: bool,
    ) -> list[EmailSendResult]:
        message_by_email = {
            message.recipient_email.lower(): message for message in email_messages
        }
        emails_payload = []
        for contact in verified_contacts:
            email = (contact.email or "").lower()
            if not email:
                continue
            message = message_by_email[email]
            emails_payload.append(
                {
                    "email": email,
                    "subject": message.subject,
                    "body": message.body,
                }
            )

        retry_config = RetryConfig(
            max_attempts=self.max_retries,
            initial_delay_seconds=0.1,
            backoff_factor=2.0,
            retryable_status_codes={429, 500, 502, 503, 504},
            enable_sleep=False,
        )
        response_payload = run_with_retry(
            lambda: self._post_fake_http(emails_payload, dry_run),
            retry_config,
        )
        results_payload = response_payload.get("results")
        if not isinstance(results_payload, list):
            raise ValueError("Fake Brevo API returned malformed result data.")

        contact_by_email = {
            (contact.email or "").lower(): contact for contact in verified_contacts if contact.email
        }
        results: list[EmailSendResult] = []
        for item in results_payload:
            if not isinstance(item, dict):
                raise ValueError("Fake Brevo API returned malformed send result entries.")
            email = str(item.get("email", "")).lower()
            contact = contact_by_email.get(email)
            if contact is None:
                raise ValueError("Fake Brevo API returned a result for an unknown email.")
            results.append(
                EmailSendResult(
                    contact_name=contact.name,
                    email=email,
                    company_domain=contact.company_domain,
                    send_status=str(item.get("send_status", "failed")),
                    provider="brevo",
                    provider_message_id=str(item.get("provider_message_id", "")),
                    failure_reason=item.get("failure_reason"),
                )
            )
        return results

    def _send_live_outreach(
        self,
        verified_contacts: list[VerifiedContact],
        email_messages: list[EmailMessage],
        dry_run: bool,
    ) -> list[EmailSendResult]:
        message_by_email = {
            message.recipient_email.lower(): message for message in email_messages
        }
        results: list[EmailSendResult] = []
        retry_config = RetryConfig(
            max_attempts=self.max_retries,
            initial_delay_seconds=1.0,
            backoff_factor=2.0,
            retryable_status_codes={429, 500, 502, 503, 504},
            enable_sleep=not dry_run,
        )

        for contact in verified_contacts:
            email = (contact.email or "").lower()
            if not email:
                continue

            message = message_by_email[email]
            if dry_run:
                results.append(
                    EmailSendResult(
                        contact_name=contact.name,
                        email=email,
                        company_domain=contact.company_domain,
                        send_status="dry_run",
                        provider="brevo",
                        provider_message_id=f"brevo-live-dry-run-{contact.company_domain.replace('.', '-')}",
                    )
                )
                continue

            try:
                response_json = run_with_retry(
                    lambda: self._post_live_message(contact, message),
                    retry_config,
                )
                results.append(
                    EmailSendResult(
                        contact_name=contact.name,
                        email=email,
                        company_domain=contact.company_domain,
                        send_status="sent",
                        provider="brevo",
                        provider_message_id=str(
                            response_json.get("messageId")
                            or response_json.get("message_id")
                            or ""
                        ),
                    )
                )
            except Exception as exc:
                results.append(
                    EmailSendResult(
                        contact_name=contact.name,
                        email=email,
                        company_domain=contact.company_domain,
                        send_status="failed",
                        provider="brevo",
                        provider_message_id="",
                        failure_reason=str(exc),
                    )
                )

        return results

    def _post_live_message(
        self,
        contact: VerifiedContact,
        message: EmailMessage,
    ) -> dict:
        payload = {
            "sender": {
                "name": self.sender_name,
                "email": self.sender_email,
            },
            "to": [
                {
                    "email": contact.email,
                    "name": contact.name,
                }
            ],
            "subject": message.subject,
            "textContent": message.body,
        }
        try:
            response = requests.post(
                BREVO_API_URL,
                headers={
                    "accept": "application/json",
                    "api-key": self.api_key,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError(
                f"Brevo temporary network error: {exc.__class__.__name__}.",
                status_code=503,
            ) from exc

        retry_after_seconds = self._parse_retry_after(response.headers.get("Retry-After"))

        if response.status_code in (200, 201, 202):
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Brevo returned malformed JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Brevo returned an unexpected response payload.")
            if "messageId" not in payload and "message_id" not in payload:
                raise ValueError("Brevo returned an unexpected response payload.")
            return payload
        if response.status_code == 400:
            raise ValueError("Brevo rejected the request with HTTP 400.")
        if response.status_code == 401:
            raise ValueError("Brevo rejected the API key with HTTP 401.")
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableOperationError(
                f"Brevo temporary error HTTP {response.status_code}.",
                status_code=response.status_code,
                retry_after_seconds=retry_after_seconds,
            )

        raise ValueError(f"Unexpected Brevo response HTTP {response.status_code}.")

    def _post_fake_http(self, emails_payload: list[dict[str, str]], dry_run: bool) -> dict:
        try:
            response = requests.post(
                f"{self.settings.fake_api_base_url.rstrip('/')}/brevo/send",
                json={"emails": emails_payload, "dry_run": dry_run},
                headers=self._build_headers(),
                params=self._build_params(),
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError("Fake Brevo API network error.", status_code=503) from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableOperationError(
                f"Fake Brevo API temporary error HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ValueError(f"Fake Brevo API returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Fake Brevo API returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Fake Brevo API returned malformed payload.")
        return payload

    def _build_headers(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"x-fake-fail": self.settings.fake_api_fail_mode}
        return {}

    def _build_params(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"fail": self.settings.fake_api_fail_mode}
        return {}

    def _parse_retry_after(self, value: str | None) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def test_connection(self) -> dict[str, object]:
        if not self.api_key:
            raise ValueError("Missing BREVO_API_KEY in .env")
        if not self.sender_email:
            raise ValueError("Missing BREVO_SENDER_EMAIL in .env")
        if not self.sender_name:
            raise ValueError("Missing BREVO_SENDER_NAME in .env")

        try:
            response = requests.get(
                BREVO_ACCOUNT_URL,
                headers={
                    "accept": "application/json",
                    "api-key": self.api_key,
                },
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ValueError(f"Brevo API: FAILED - network error ({exc.__class__.__name__})") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Brevo API: FAILED - malformed JSON response") from exc
            if not isinstance(payload, dict):
                raise ValueError("Brevo API: FAILED - malformed payload")
            return {
                "status": "ok",
                "message": "Brevo API: OK",
                "account_email": payload.get("email"),
                "company_name": payload.get("companyName"),
                "plan": payload.get("plan"),
                "sender_email_configured": self.sender_email,
                "sender_name_configured": self.sender_name,
            }
        if response.status_code in {401, 403}:
            raise ValueError(f"Brevo API: FAILED - authentication error (HTTP {response.status_code})")
        if response.status_code == 429:
            raise ValueError("Brevo API: FAILED - rate limited (HTTP 429)")
        if response.status_code in {500, 502, 503, 504}:
            raise ValueError(f"Brevo API: FAILED - server error (HTTP {response.status_code})")

        raise ValueError(f"Brevo API: FAILED - unexpected HTTP {response.status_code}")

    def send_test_email(self, recipient_email: str) -> EmailSendResult:
        contact = VerifiedContact(
            name="Brevo Test Recipient",
            title="Test Recipient",
            company_name="Local Test",
            company_domain=recipient_email.split("@")[-1],
            linkedin_url=None,
            email=recipient_email,
            verification_status="verified",
            source_provider="brevo_test",
        )
        message = EmailMessage(
            contact_name="Brevo Test Recipient",
            company_domain=contact.company_domain,
            recipient_email=recipient_email,
            subject="Vocallabs Pipeline Brevo Test",
            body="This is a test email from the local automated outreach pipeline.",
        )
        return self._send_live_outreach([contact], [message], dry_run=False)[0]
