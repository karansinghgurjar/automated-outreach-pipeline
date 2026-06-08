"""Prospeo service layer."""

from __future__ import annotations

from math import ceil
import requests

from app.config import get_settings
from app.models import Company, Contact
from app.utils.retry import RetryConfig, RetryableOperationError, run_with_retry
from app.utils.validators import normalize_domain


TITLE_POOL = [
    "Founder",
    "CEO",
    "CTO",
    "VP Engineering",
    "VP Sales",
    "Head of Growth",
    "Chief Revenue Officer",
    "VP Marketing",
]

NAME_POOL = [
    "Ava Patel",
    "Noah Kim",
    "Mia Johnson",
    "Liam Chen",
    "Sophia Davis",
    "Ethan Walker",
    "Isabella Singh",
    "Lucas Rivera",
]

PROSPEO_SEARCH_PERSON_URL = "https://api.prospeo.io/search-person"
PROSPEO_ACCOUNT_INFO_URL = "https://api.prospeo.io/account-information"
PROSPEO_ENRICH_PERSON_URL = "https://api.prospeo.io/enrich-person"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ProspeoService:
    """Handles decision-maker enrichment via Prospeo."""

    def __init__(
        self,
        mode: str = "mock",
        max_contacts_per_company: int = 2,
        simulate_failures: bool = False,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.mode = mode
        self.max_contacts_per_company = max_contacts_per_company
        self.simulate_failures = simulate_failures
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.settings = get_settings()
        self.last_run_stats: dict[str, object] = {}

    def find_decision_makers(
        self,
        companies: list[Company] | list[str],
        limit_contacts: int,
        max_contacts_per_company: int | None = None,
    ) -> list[Contact]:
        """Return deterministic mock decision-makers."""
        company_domains = [
            company.domain if isinstance(company, Company) else str(company)
            for company in companies
        ]
        per_company_limit = max_contacts_per_company or self.max_contacts_per_company
        self.last_run_stats = {
            "mode": self.mode,
            "companies_with_contacts": 0,
            "companies_failed": 0,
            "errors": [],
        }
        if self.mode == "fake_http":
            return self._find_fake_http_decision_makers(company_domains, limit_contacts)
        if self.mode == "live":
            return self._find_live_decision_makers(company_domains, limit_contacts, per_company_limit)
        if self.mode != "mock":
            raise NotImplementedError(f"Unsupported Prospeo mode: {self.mode}")

        contacts: list[Contact] = []
        generated_count = 0
        companies_with_contacts = 0

        for company_index, company_domain in enumerate(company_domains):
            if self.simulate_failures and company_index == 1:
                continue

            company_name = self._company_name_from_domain(company_domain)
            company_generated = 0
            for offset in range(per_company_limit):
                if generated_count >= limit_contacts:
                    self.last_run_stats["companies_with_contacts"] = companies_with_contacts
                    return contacts

                name = NAME_POOL[(generated_count + offset) % len(NAME_POOL)]
                title = TITLE_POOL[(generated_count + offset) % len(TITLE_POOL)]
                slug = name.lower().replace(" ", "-")
                contacts.append(
                    Contact(
                        name=name,
                        title=title,
                        company_name=company_name,
                        company_domain=company_domain,
                        linkedin_url=f"https://www.linkedin.com/in/{slug}-{company_name.lower().replace(' ', '-')}",
                        email=None,
                        verification_status="unresolved",
                        source_provider="prospeo",
                    )
                )
                generated_count += 1
                company_generated += 1

            if company_generated:
                companies_with_contacts += 1

        self.last_run_stats["companies_with_contacts"] = companies_with_contacts
        return contacts

    def _company_name_from_domain(self, company_domain: str) -> str:
        company_stem = company_domain.split(".")[0].replace("-", " ")
        return " ".join(part.capitalize() for part in company_stem.split())

    def _find_fake_http_decision_makers(
        self,
        company_domains: list[str],
        limit_contacts: int,
    ) -> list[Contact]:
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay_seconds=0.1,
            backoff_factor=2.0,
            retryable_status_codes={429, 500, 502, 503, 504},
            enable_sleep=False,
        )
        response_payload = run_with_retry(
            lambda: self._post_fake_http(company_domains),
            retry_config,
        )
        contacts_payload = response_payload.get("contacts")
        if not isinstance(contacts_payload, list):
            raise ValueError("Fake Prospeo API returned malformed contact data.")

        contacts: list[Contact] = []
        for item in contacts_payload[:limit_contacts]:
            if not isinstance(item, dict):
                raise ValueError("Fake Prospeo API returned malformed contact entries.")
            contacts.append(
                Contact(
                    name=str(item.get("name", "")),
                    title=str(item.get("title", "")),
                    company_name=self._company_name_from_domain(str(item.get("company_domain", ""))),
                    company_domain=str(item.get("company_domain", "")),
                    linkedin_url=item.get("linkedin_url"),
                    email=item.get("email"),
                    verification_status="verified" if item.get("email") else "unresolved",
                    source_provider="prospeo",
                )
            )
        self.last_run_stats["companies_with_contacts"] = len({contact.company_domain for contact in contacts})
        return contacts

    def _find_live_decision_makers(
        self,
        company_domains: list[str],
        limit_contacts: int,
        per_company_limit: int,
    ) -> list[Contact]:
        if not self.settings.prospeo_api_key:
            raise ValueError("PROSPEO_API_KEY is required for live Prospeo mode.")

        contacts: list[Contact] = []
        companies_with_contacts = 0
        errors: list[dict[str, str]] = []

        for company_domain in company_domains:
            normalized_domain = normalize_domain(company_domain)
            remaining_contacts = limit_contacts - len(contacts)
            if remaining_contacts <= 0:
                break

            requested_per_company_limit = min(per_company_limit, remaining_contacts)
            try:
                company_contacts = self._search_live_company_contacts(
                    normalized_domain,
                    requested_per_company_limit,
                )
            except Exception as exc:
                errors.append(
                    {
                        "company_domain": normalized_domain,
                        "error": str(exc),
                    }
                )
                continue

            if company_contacts:
                companies_with_contacts += 1
                contacts.extend(company_contacts[:remaining_contacts])

        self.last_run_stats = {
            "mode": "live",
            "companies_with_contacts": companies_with_contacts,
            "companies_failed": len(errors),
            "errors": errors,
        }
        return contacts

    def _search_live_company_contacts(
        self,
        company_domain: str,
        per_company_limit: int,
    ) -> list[Contact]:
        contacts: list[Contact] = []
        max_pages = max(1, min(5, ceil(per_company_limit / 25)))

        for page in range(1, max_pages + 1):
            retry_config = RetryConfig(
                max_attempts=self.max_retries,
                initial_delay_seconds=0.5,
                backoff_factor=2.0,
                retryable_status_codes=RETRYABLE_STATUS_CODES,
                enable_sleep=True,
            )
            payload = run_with_retry(
                lambda page_number=page: self._post_live_search(company_domain, page_number),
                retry_config,
            )
            page_contacts = self._map_live_search_results(payload, company_domain)
            enriched_contacts = [self._enrich_live_contact(contact) for contact in page_contacts]
            contacts.extend(enriched_contacts)
            if len(contacts) >= per_company_limit:
                break

            pagination = payload.get("pagination")
            if not isinstance(pagination, dict):
                break
            current_page = pagination.get("current_page", page)
            total_pages = pagination.get("total_page") or pagination.get("total_pages") or page
            try:
                if int(current_page) >= int(total_pages):
                    break
            except (TypeError, ValueError):
                break

        return contacts[:per_company_limit]

    def _post_live_search(self, company_domain: str, page: int) -> dict:
        payload = {
            "page": page,
            "filters": {
                "company": {
                    "websites": {
                        "include": [normalize_domain(company_domain)],
                    }
                },
                "person_job_title": {
                    "include": TITLE_POOL,
                    "match_mode": "CONTAINS",
                },
                "person_seniority": {
                    "include": ["C-Suite", "Founder/Owner", "Vice President"],
                },
            },
        }

        try:
            response = requests.post(
                PROSPEO_SEARCH_PERSON_URL,
                headers={
                    "X-KEY": self.settings.prospeo_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError(
                f"Prospeo network error for {company_domain}.",
                status_code=503,
            ) from exc

        retry_after_seconds = self._parse_retry_after(response.headers.get("Retry-After"))
        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableOperationError(
                f"Prospeo temporary error HTTP {response.status_code} for {company_domain}.",
                status_code=response.status_code,
                retry_after_seconds=retry_after_seconds,
            )
        if response.status_code == 401:
            raise ValueError("Prospeo rejected the API key with HTTP 401.")

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise ValueError(f"Prospeo returned malformed JSON for {company_domain}.") from exc

        if not isinstance(response_payload, dict):
            raise ValueError(f"Prospeo returned malformed payload for {company_domain}.")

        if response.status_code == 400:
            error_code = response_payload.get("error_code")
            if error_code == "NO_RESULTS":
                return {"results": [], "pagination": {"current_page": page, "total_page": page}}
            message = response_payload.get("filter_error") or response_payload.get("message") or error_code
            raise ValueError(f"Prospeo request failed for {company_domain}: {message or 'HTTP 400'}")

        if response.status_code != 200:
            raise ValueError(f"Prospeo returned HTTP {response.status_code} for {company_domain}.")

        return response_payload

    def _map_live_search_results(
        self,
        payload: dict,
        requested_company_domain: str,
    ) -> list[Contact]:
        results = payload.get("results")
        if results is None:
            return []
        if not isinstance(results, list):
            raise ValueError(f"Prospeo returned malformed results for {requested_company_domain}.")

        contacts: list[Contact] = []
        for item in results:
            if not isinstance(item, dict):
                continue

            person = item.get("person")
            company = item.get("company")
            if not isinstance(person, dict):
                continue
            if company is not None and not isinstance(company, dict):
                company = {}

            full_name = str(person.get("full_name") or "").strip()
            first_name = str(person.get("first_name") or "").strip()
            last_name = str(person.get("last_name") or "").strip()
            name = full_name or " ".join(part for part in [first_name, last_name] if part).strip()
            title = str(
                person.get("current_job_title")
                or person.get("job_title")
                or person.get("headline")
                or ""
            ).strip()
            linkedin_url = person.get("linkedin_url") or person.get("linkedin")
            email = (
                person.get("email")
                or person.get("professional_email")
                or person.get("work_email")
                or item.get("email")
            )

            company_domain = str(
                (company or {}).get("domain")
                or (company or {}).get("website")
                or requested_company_domain
            ).strip()
            company_domain = normalize_domain(company_domain)
            company_name = str((company or {}).get("name") or self._company_name_from_domain(company_domain)).strip()

            if not name or not title:
                continue

            contacts.append(
                Contact(
                    name=name,
                    title=title,
                    company_name=company_name,
                    company_domain=company_domain,
                    linkedin_url=str(linkedin_url).strip() if linkedin_url else None,
                    email=str(email).strip().lower() if email else None,
                    verification_status="verified" if email else "unresolved",
                    source_provider="prospeo",
                    failure_reason=None if email else "Prospeo did not return an email",
                    metadata={
                        "provider": "prospeo",
                        "source_mode": "live",
                        "person_id": person.get("id") or person.get("person_id"),
                        "first_name": first_name or None,
                        "last_name": last_name or None,
                        "email_status": person.get("email_status"),
                    },
                )
            )

        return contacts

    def _enrich_live_contact(self, contact: Contact) -> Contact:
        if contact.email:
            return contact

        retry_config = RetryConfig(
            max_attempts=self.max_retries,
            initial_delay_seconds=0.5,
            backoff_factor=2.0,
            retryable_status_codes=RETRYABLE_STATUS_CODES,
            enable_sleep=True,
        )
        try:
            payload = run_with_retry(
                lambda: self._post_live_enrich(contact),
                retry_config,
            )
        except ValueError as exc:
            message = str(exc)
            if "NO_MATCH" in message:
                contact.failure_reason = "Prospeo did not return an email"
                contact.verification_status = "unresolved"
                return contact
            raise

        person = payload.get("person")
        if not isinstance(person, dict):
            return contact

        email_payload = person.get("email")
        if isinstance(email_payload, dict):
            email_value = email_payload.get("email")
            email_status = str(email_payload.get("status") or "").strip().lower()
            if email_value:
                contact.email = str(email_value).strip().lower()
                contact.verification_status = "verified" if email_status == "verified" else "unresolved"
                contact.failure_reason = None if contact.email else "Prospeo did not return an email"
                contact.metadata["email_status"] = email_status or None
            else:
                contact.verification_status = "unresolved"
                contact.failure_reason = "Prospeo did not return an email"
                contact.metadata["email_status"] = email_status or "unavailable"

        linkedin_url = person.get("linkedin_url") or person.get("linkedin")
        if linkedin_url and not contact.linkedin_url:
            contact.linkedin_url = str(linkedin_url).strip()
        return contact

    def _post_live_enrich(self, contact: Contact) -> dict:
        payload = {
            "only_verified_email": False,
            "enrich_mobile": False,
            "data": self._build_enrich_identity(contact),
        }
        try:
            response = requests.post(
                PROSPEO_ENRICH_PERSON_URL,
                headers={
                    "X-KEY": self.settings.prospeo_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError(
                f"Prospeo enrich network error for {contact.company_domain}.",
                status_code=503,
            ) from exc

        retry_after_seconds = self._parse_retry_after(response.headers.get("Retry-After"))
        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableOperationError(
                f"Prospeo enrich temporary error HTTP {response.status_code} for {contact.company_domain}.",
                status_code=response.status_code,
                retry_after_seconds=retry_after_seconds,
            )
        if response.status_code in {401, 403}:
            raise ValueError(f"Prospeo rejected the API key with HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"Prospeo enrich returned malformed JSON for {contact.company_domain}.") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Prospeo enrich returned malformed payload for {contact.company_domain}.")

        if response.status_code == 400:
            error_code = payload.get("error_code")
            raise ValueError(f"Prospeo enrich failed for {contact.company_domain}: {error_code or 'HTTP 400'}")
        if response.status_code != 200:
            raise ValueError(f"Prospeo enrich returned HTTP {response.status_code} for {contact.company_domain}.")
        return payload

    def _build_enrich_identity(self, contact: Contact) -> dict[str, str]:
        person_id = contact.metadata.get("person_id")
        if person_id:
            return {"person_id": str(person_id)}

        identity: dict[str, str] = {"company_website": contact.company_domain}
        first_name = contact.metadata.get("first_name")
        last_name = contact.metadata.get("last_name")
        if first_name:
            identity["first_name"] = str(first_name)
        if last_name:
            identity["last_name"] = str(last_name)
        if not first_name and not last_name:
            parts = contact.name.strip().split()
            if parts:
                identity["first_name"] = parts[0]
                if len(parts) > 1:
                    identity["last_name"] = parts[-1]
        return identity

    def _post_fake_http(self, company_domains: list[str]) -> dict:
        try:
            response = requests.post(
                f"{self.settings.fake_api_base_url.rstrip('/')}/prospeo/decision-makers",
                json={"domains": company_domains},
                headers=self._build_headers(),
                params=self._build_params(),
                timeout=30,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError("Fake Prospeo API network error.", status_code=503) from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableOperationError(
                f"Fake Prospeo API temporary error HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ValueError(f"Fake Prospeo API returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Fake Prospeo API returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Fake Prospeo API returned malformed payload.")
        return payload

    def _parse_retry_after(self, value: str | None) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _build_headers(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"x-fake-fail": self.settings.fake_api_fail_mode}
        return {}

    def _build_params(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"fail": self.settings.fake_api_fail_mode}
        return {}

    def test_connection(self, timeout_seconds: float | None = None) -> dict[str, object]:
        if not self.settings.prospeo_api_key:
            raise ValueError("Missing PROSPEO_API_KEY in .env")

        try:
            response = requests.get(
                PROSPEO_ACCOUNT_INFO_URL,
                headers={"X-KEY": self.settings.prospeo_api_key},
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ValueError(f"Prospeo API: FAILED - network error ({exc.__class__.__name__})") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Prospeo API: FAILED - malformed JSON response") from exc
            if not isinstance(payload, dict):
                raise ValueError("Prospeo API: FAILED - malformed payload")
            account = payload.get("response")
            if not isinstance(account, dict):
                raise ValueError("Prospeo API: FAILED - malformed account payload")
            return {
                "status": "ok",
                "message": "Prospeo API: OK",
                "current_plan": account.get("current_plan"),
                "remaining_credits": account.get("remaining_credits"),
                "used_credits": account.get("used_credits"),
            }
        if response.status_code == 400:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Prospeo API: FAILED - malformed JSON response") from exc
            if isinstance(payload, dict) and payload.get("error_code") == "INVALID_API_KEY":
                raise ValueError("Prospeo API: FAILED - invalid API key")
            raise ValueError("Prospeo API: FAILED - invalid request (HTTP 400)")
        if response.status_code in {401, 403}:
            raise ValueError(f"Prospeo API: FAILED - authentication error (HTTP {response.status_code})")
        if response.status_code == 429:
            raise ValueError("Prospeo API: FAILED - rate limited (HTTP 429)")
        if response.status_code in {500, 502, 503, 504}:
            raise ValueError(f"Prospeo API: FAILED - server error (HTTP {response.status_code})")

        raise ValueError(f"Prospeo API: FAILED - unexpected HTTP {response.status_code}")
