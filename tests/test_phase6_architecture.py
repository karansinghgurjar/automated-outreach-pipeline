from argparse import Namespace

from app.pipeline import OutreachPipeline
from main import resolve_service_modes


def test_default_cli_modes_skip_eazyreach() -> None:
    args = Namespace(
        fake_http=False,
        live=False,
        live_ocean=False,
        live_prospeo=False,
        live_eazyreach=False,
        live_brevo=False,
        send_live=False,
        mock_ocean=False,
        mock_prospeo=False,
        mock_eazyreach=False,
        mock_brevo=False,
        source="csv",
    )

    service_modes = resolve_service_modes(args)

    assert service_modes["ocean"] == "csv"
    assert service_modes["prospeo"] == "mock"
    assert service_modes["eazyreach"] == "skipped"
    assert service_modes["brevo"] == "mock"


def test_pipeline_skips_eazyreach_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="openai.com",
        service_modes={"ocean": "csv", "prospeo": "mock", "eazyreach": "skipped", "brevo": "mock"},
        limit_companies=3,
        limit_contacts=6,
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

    assert summary.pipeline_version == "ocean_prospeo_brevo"
    assert summary.eazyreach_required is False
    assert summary.eazyreach_mode == "skipped"
    assert summary.contacts_without_email == summary.contacts_found
    assert summary.emails_ready_for_brevo == 0
