from pathlib import Path

from app.pipeline import OutreachPipeline

import pytest


def test_csv_ocean_source_pipeline_completes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": "csv", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=True,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )

    summary = pipeline.run()

    assert summary.ocean_source == "csv"
    assert summary.companies_found == 5


def test_csv_ocean_missing_file_fails_gracefully(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.services.ocean.CSV_PATH", tmp_path / "missing.csv")
    pipeline = OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": "csv", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=True,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )

    summary = pipeline.run()

    assert summary.ocean_status["status"] == "failed"
    assert "missing" in (summary.ocean_status["error_message"] or "").lower()


def test_csv_ocean_malformed_file_fails_gracefully(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    malformed_csv = tmp_path / "bad_seed_companies.csv"
    malformed_csv.write_text("wrong,headers\nfoo,bar\n", encoding="utf-8")
    monkeypatch.setattr("app.services.ocean.CSV_PATH", malformed_csv)
    pipeline = OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": "csv", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=True,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )

    summary = pipeline.run()

    assert summary.ocean_status["status"] == "failed"
    assert "headers" in (summary.ocean_status["error_message"] or "").lower()
