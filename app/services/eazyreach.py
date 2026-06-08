"""Eazyreach service layer."""

from __future__ import annotations

import requests

from app.config import get_settings
from app.models import Contact, VerifiedContact
from app.utils.retry import RetryConfig, RetryableOperationError, run_with_retry


class EazyreachService:
    """Handles email discovery and verification via Eazyreach."""

    def __init__(self, mode: str = "mock", simulate_failures: bool = False) -> None:
        self.mode = mode
        self.simulate_failures = simulate_failures
        self.settings = get_settings()

    def resolve_emails(self, contacts: list[Contact]) -> list[VerifiedContact]:
        """Return deterministic mock email verification results."""
        if self.mode == "fake_http":
            return self._resolve_fake_http_emails(contacts)
        if self.mode != "mock":
            # TODO: Implement real Eazyreach email resolution API call.
            raise NotImplementedError("Live Eazyreach integration is not implemented yet.")

        resolved: list[VerifiedContact] = []

        for index, contact in enumerate(contacts):
            try:
                if not contact.linkedin_url:
                    resolved.append(
                        VerifiedContact(
                            name=contact.name,
                            title=contact.title,
                            company_name=contact.company_name,
                            company_domain=contact.company_domain,
                            linkedin_url=contact.linkedin_url,
                            email=None,
                            verification_status="unresolved",
                            failure_reason="Missing LinkedIn URL",
                            metadata={"resolver_mode": "mock/fallback"},
                        )
                    )
                    continue

                first_name, last_name = self._split_name(contact.name)
                should_unresolve = index == 0 or index % 7 == 0
                if self.simulate_failures and index == 2:
                    should_unresolve = True

                if should_unresolve:
                    resolved.append(
                        VerifiedContact(
                            name=contact.name,
                            title=contact.title,
                            company_name=contact.company_name,
                            company_domain=contact.company_domain,
                            linkedin_url=contact.linkedin_url,
                            email=None,
                            verification_status="unresolved",
                            failure_reason="No verified email found",
                            metadata={"resolver_mode": "mock/fallback"},
                        )
                    )
                    continue

                if index % 2 == 0:
                    email = f"{first_name}.{last_name}@{contact.company_domain}"
                else:
                    email = f"{first_name}@{contact.company_domain}"

                resolved.append(
                    VerifiedContact(
                        name=contact.name,
                        title=contact.title,
                        company_name=contact.company_name,
                        company_domain=contact.company_domain,
                        linkedin_url=contact.linkedin_url,
                        email=email.lower(),
                        verification_status="mock_verified",
                        metadata={"resolver_mode": "mock/fallback"},
                    )
                )
            except Exception as exc:
                resolved.append(
                    VerifiedContact(
                        name=contact.name,
                        title=contact.title,
                        company_name=contact.company_name,
                        company_domain=contact.company_domain,
                        linkedin_url=contact.linkedin_url,
                        email=None,
                        verification_status="unresolved",
                        failure_reason=str(exc),
                        metadata={"resolver_mode": "mock/fallback"},
                    )
                )

        return resolved

    def _split_name(self, name: str) -> tuple[str, str]:
        parts = name.strip().lower().split()
        first_name = parts[0]
        last_name = parts[-1] if len(parts) > 1 else "team"
        return first_name, last_name

    def _resolve_fake_http_emails(self, contacts: list[Contact]) -> list[VerifiedContact]:
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay_seconds=0.1,
            backoff_factor=2.0,
            retryable_status_codes={429, 500, 502, 503, 504},
            enable_sleep=False,
        )
        response_payload = run_with_retry(
            lambda: self._post_fake_http(contacts),
            retry_config,
        )
        verified_payload = response_payload.get("verified_contacts")
        unresolved_payload = response_payload.get("unresolved_contacts")
        if not isinstance(verified_payload, list) or not isinstance(unresolved_payload, list):
            raise ValueError("Fake Eazyreach API returned malformed contact data.")

        resolved: list[VerifiedContact] = []
        for item in verified_payload:
            if not isinstance(item, dict):
                raise ValueError("Fake Eazyreach API returned malformed verified contact entries.")
            resolved.append(
                VerifiedContact(
                    name=str(item.get("name", "")),
                    title=str(item.get("title", "")),
                    company_name=self._company_name_from_domain(str(item.get("company_domain", ""))),
                    company_domain=str(item.get("company_domain", "")),
                    linkedin_url=item.get("linkedin_url"),
                    email=item.get("email"),
                    verification_status=str(item.get("verification_status", "")),
                    metadata={"resolver_mode": "fake_http"},
                )
            )
        for item in unresolved_payload:
            if not isinstance(item, dict):
                raise ValueError("Fake Eazyreach API returned malformed unresolved contact entries.")
            resolved.append(
                VerifiedContact(
                    name=str(item.get("name", "")),
                    title=str(item.get("title", "")),
                    company_name=self._company_name_from_domain(str(item.get("company_domain", ""))),
                    company_domain=str(item.get("company_domain", "")),
                    linkedin_url=item.get("linkedin_url"),
                    email=item.get("email"),
                    verification_status=str(item.get("verification_status", "unresolved")),
                    failure_reason=item.get("failure_reason"),
                    metadata={"resolver_mode": "fake_http"},
                )
            )
        return resolved

    def _post_fake_http(self, contacts: list[Contact]) -> dict:
        payload = {
            "contacts": [
                {
                    "name": contact.name,
                    "title": contact.title,
                    "company_domain": contact.company_domain,
                    "linkedin_url": contact.linkedin_url,
                }
                for contact in contacts
            ]
        }
        try:
            response = requests.post(
                f"{self.settings.fake_api_base_url.rstrip('/')}/eazyreach/resolve",
                json=payload,
                headers=self._build_headers(),
                params=self._build_params(),
                timeout=30,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError("Fake Eazyreach API network error.", status_code=503) from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableOperationError(
                f"Fake Eazyreach API temporary error HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ValueError(f"Fake Eazyreach API returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Fake Eazyreach API returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Fake Eazyreach API returned malformed payload.")
        return payload

    def _build_headers(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"x-fake-fail": self.settings.fake_api_fail_mode}
        return {}

    def _build_params(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"fail": self.settings.fake_api_fail_mode}
        return {}

    def _company_name_from_domain(self, company_domain: str) -> str:
        company_stem = company_domain.split(".")[0].replace("-", " ")
        return " ".join(part.capitalize() for part in company_stem.split())
