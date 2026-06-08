from app.utils.validators import normalize_domain, validate_domain

import pytest


def test_valid_domain_passes() -> None:
    assert validate_domain("Notion.so") == "notion.so"


def test_domain_normalization_handles_common_prefixes() -> None:
    assert normalize_domain("https://www.notion.so/") == "notion.so"
    assert normalize_domain("www.notion.so") == "notion.so"
    assert normalize_domain("notion.so/") == "notion.so"


def test_invalid_domain_fails() -> None:
    with pytest.raises(ValueError):
        validate_domain("invalid domain")
