"""Validation helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse


DOMAIN_PATTERN = re.compile(r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$")


def normalize_domain(domain: str) -> str:
    """Normalize common user input forms into a bare domain."""
    cleaned = domain.strip().lower()
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    hostname = (parsed.netloc or parsed.path).strip().lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    hostname = hostname.rstrip("/")
    return hostname


def validate_domain(domain: str) -> str:
    """Validate and normalize a seed domain."""
    cleaned = normalize_domain(domain)
    if not DOMAIN_PATTERN.match(cleaned):
        raise ValueError(
            f"'{domain}' is not a valid domain. Example: notion.so or github.com."
        )
    return cleaned


def ensure_positive_limit(value: int, argument_name: str) -> int:
    """Ensure a numeric CLI limit is positive."""
    if value <= 0:
        raise ValueError(f"{argument_name} must be greater than 0.")
    return value


def ensure_positive_timeout(value: float) -> float:
    """Ensure the timeout is positive."""
    if value <= 0:
        raise ValueError("timeout must be greater than 0.")
    return value


def normalize_email(email: str | None) -> str | None:
    """Normalize an email string for deduplication."""
    if not email:
        return None
    return email.strip().lower()
