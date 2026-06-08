"""Ocean service layer."""

from __future__ import annotations

from csv import DictReader
import logging
from pathlib import Path
import requests

from app.config import get_settings
from app.models import Company
from app.utils.retry import RetryConfig, RetryableOperationError, run_with_retry
from app.utils.validators import normalize_domain, validate_domain


KNOWN_LOOKALIKES: dict[str, list[tuple[str, str]]] = {
    "notion.so": [
        ("Airtable", "airtable.com"),
        ("ClickUp", "clickup.com"),
        ("Monday.com", "monday.com"),
        ("Asana", "asana.com"),
        ("Coda", "coda.io"),
    ],
    "github.com": [
        ("GitLab", "gitlab.com"),
        ("Bitbucket", "bitbucket.org"),
        ("Linear", "linear.app"),
        ("Vercel", "vercel.com"),
        ("Replit", "replit.com"),
    ],
}

CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_companies.csv"
OCEAN_CREDIT_BALANCE_URL = "https://api.ocean.io/v2/credits/balance"


class OceanService:
    """Handles company discovery via Ocean."""

    def __init__(self, mode: str = "mock") -> None:
        self.mode = mode
        self.settings = get_settings()

    def find_lookalike_companies(self, seed_domain: str, limit_companies: int) -> list[Company]:
        """Return deterministic mock lookalike companies."""
        if self.mode == "fake_http":
            return self._find_fake_http_lookalikes(seed_domain, limit_companies)
        if self.mode == "csv":
            return self._find_csv_lookalikes(seed_domain, limit_companies)
        if self.mode != "mock":
            # TODO: Implement real Ocean.io company lookalike API call.
            raise NotImplementedError("Live Ocean integration is not implemented yet.")

        matches = KNOWN_LOOKALIKES.get(seed_domain, self._build_fallback_domains(seed_domain))
        companies = [
            Company(
                name=name,
                domain=normalize_domain(domain),
                similarity_reason=f"Mock lookalike for {seed_domain}",
                industry="B2B SaaS",
                description=f"{name} is a plausible peer for {seed_domain}.",
            )
            for name, domain in matches[:limit_companies]
        ]
        return companies

    def _build_fallback_domains(self, seed_domain: str) -> list[tuple[str, str]]:
        stem = seed_domain.split(".")[0].replace("-", "")
        return [
            (f"{stem.title()}Flow", f"{stem}flow.com"),
            (f"{stem.title()}Cloud", f"{stem}cloud.io"),
            (f"{stem.title()}Works", f"{stem}works.com"),
            (f"{stem.title()}Labs", f"{stem}labs.ai"),
            (f"{stem.title()}HQ", f"{stem}hq.com"),
        ]

    def _find_fake_http_lookalikes(self, seed_domain: str, limit_companies: int) -> list[Company]:
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay_seconds=0.1,
            backoff_factor=2.0,
            retryable_status_codes={429, 500, 502, 503, 504},
            enable_sleep=False,
        )
        response_payload = run_with_retry(
            lambda: self._post_fake_http(seed_domain),
            retry_config,
        )
        companies_payload = response_payload.get("companies")
        if not isinstance(companies_payload, list):
            raise ValueError("Fake Ocean API returned malformed company data.")

        companies: list[Company] = []
        for item in companies_payload[:limit_companies]:
            if not isinstance(item, dict) or "domain" not in item or "name" not in item:
                raise ValueError("Fake Ocean API returned malformed company entries.")
            companies.append(
                Company(
                    name=str(item["name"]),
                    domain=normalize_domain(str(item["domain"])),
                    similarity_reason=f"Fake HTTP lookalike for {seed_domain}",
                    industry="B2B SaaS",
                )
            )

        return companies

    def _post_fake_http(self, seed_domain: str) -> dict:
        try:
            response = requests.post(
                f"{self.settings.fake_api_base_url.rstrip('/')}/ocean/lookalikes",
                json={"domain": seed_domain},
                headers=self._build_headers(),
                params=self._build_params(),
                timeout=30,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableOperationError("Fake Ocean API network error.", status_code=503) from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableOperationError(
                f"Fake Ocean API temporary error HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ValueError(f"Fake Ocean API returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Fake Ocean API returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Fake Ocean API returned malformed payload.")
        return payload

    def _build_headers(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"x-fake-fail": self.settings.fake_api_fail_mode}
        return {}

    def _build_params(self) -> dict[str, str]:
        if self.settings.fake_api_fail_mode:
            return {"fail": self.settings.fake_api_fail_mode}
        return {}

    def _find_csv_lookalikes(self, seed_domain: str, limit_companies: int) -> list[Company]:
        if not CSV_PATH.exists():
            raise ValueError(f"Ocean CSV source file is missing: {CSV_PATH}")

        try:
            with CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
                reader = DictReader(csv_file)
                if reader.fieldnames is None:
                    raise ValueError("Ocean CSV source is empty.")
                expected_headers = {"domain", "name"}
                if set(reader.fieldnames) != expected_headers:
                    raise ValueError(
                        "Ocean CSV source must contain exactly these headers: domain,name"
                    )

                companies: list[Company] = []
                seen_domains: set[str] = set()
                for row_number, row in enumerate(reader, start=2):
                    if not row:
                        continue
                    raw_domain = (row.get("domain") or "").strip()
                    raw_name = (row.get("name") or "").strip()
                    if not raw_domain or not raw_name:
                        raise ValueError(f"Ocean CSV source has an incomplete row at line {row_number}.")

                    normalized_domain = validate_domain(raw_domain)
                    if normalized_domain in seen_domains:
                        continue

                    seen_domains.add(normalized_domain)
                    companies.append(
                        Company(
                            name=raw_name,
                            domain=normalized_domain,
                            similarity_reason=f"CSV fallback lookalike for {seed_domain}",
                            industry="AI Infrastructure",
                            description=f"{raw_name} loaded from CSV fallback source.",
                        )
                    )

                if not companies:
                    raise ValueError("Ocean CSV source did not contain any valid companies.")

                companies = companies[:limit_companies]
                logging.getLogger("vocallabs.pipeline").info(
                    "Ocean CSV source loaded %s companies from %s",
                    len(companies),
                    CSV_PATH,
                )
                return companies
        except UnicodeDecodeError as exc:
            raise ValueError("Ocean CSV source could not be decoded as UTF-8.") from exc

    def test_connection(self, timeout_seconds: float = 15.0) -> dict[str, object]:
        if not self.settings.ocean_api_key:
            raise ValueError("Missing OCEAN_API_KEY in .env")

        try:
            response = requests.get(
                OCEAN_CREDIT_BALANCE_URL,
                params={"credit_type": "search"},
                headers={"x-api-token": self.settings.ocean_api_key},
                timeout=timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ValueError(f"Ocean API: FAILED - network error ({exc.__class__.__name__})") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError("Ocean API: FAILED - malformed JSON response") from exc
            if not isinstance(payload, dict):
                raise ValueError("Ocean API: FAILED - malformed payload")
            return {
                "status": "ok",
                "message": "Ocean API: OK",
                "payload": payload,
            }
        if response.status_code in {401, 403}:
            if response.status_code == 403:
                raise ValueError(
                    "Ocean API: FAILED - HTTP 403. Token/account exists but may not have permission "
                    "for this endpoint. Use --source csv until Ocean API access is resolved."
                )
            raise ValueError("Ocean API: FAILED - authentication error (HTTP 401)")
        if response.status_code == 429:
            raise ValueError("Ocean API: FAILED - rate limited (HTTP 429)")
        if response.status_code in {500, 502, 503, 504}:
            raise ValueError(f"Ocean API: FAILED - server error (HTTP {response.status_code})")

        raise ValueError(f"Ocean API: FAILED - unexpected HTTP {response.status_code}")
