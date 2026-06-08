from pathlib import Path
import json

from app.pipeline import OutreachPipeline


def run_pipeline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="notion.so",
        service_modes={"ocean": "mock", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
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
    pipeline.run()


def test_reports_are_created(tmp_path, monkeypatch) -> None:
    run_pipeline(tmp_path, monkeypatch)

    assert len(list((tmp_path / "outputs" / "runs").glob("*_summary.json"))) == 1
    assert len(list((tmp_path / "outputs" / "runs").glob("*_contacts.csv"))) == 1
    assert len(list((tmp_path / "outputs" / "logs").glob("*_pipeline.log"))) == 1


def test_json_summary_contains_required_fields(tmp_path, monkeypatch) -> None:
    run_pipeline(tmp_path, monkeypatch)
    json_path = next((tmp_path / "outputs" / "runs").glob("*_summary.json"))
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    for key in [
        "seed_domain",
        "started_at",
        "finished_at",
        "mock_mode",
        "dry_run",
        "companies_found",
        "contacts_found",
        "verified_emails",
        "unresolved_contacts",
        "duplicates_removed",
        "emails_ready",
        "emails_ready_for_brevo",
        "emails_sent",
        "emails_failed",
        "pipeline_version",
        "eazyreach_required",
        "companies_queried",
        "duplicate_contacts_removed",
        "duplicate_emails_removed",
        "prospeo_contacts_found",
        "prospeo_emails_found",
        "contacts_without_email",
        "send_live",
        "blocked_unverified_count",
        "eazyreach_mode",
        "brevo_mode",
        "mock_verified_count",
        "stage_statuses",
        "failed_contacts",
        "send_results",
    ]:
        assert key in payload


def test_csv_contains_required_columns(tmp_path, monkeypatch) -> None:
    run_pipeline(tmp_path, monkeypatch)
    csv_path = next((tmp_path / "outputs" / "runs").glob("*_contacts.csv"))
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]

    for column in [
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
    ]:
        assert column in header
