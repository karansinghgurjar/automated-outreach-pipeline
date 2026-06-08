from app.pipeline import OutreachPipeline


def build_pipeline(dry_run: bool = True, simulate_failures: bool = False) -> OutreachPipeline:
    return OutreachPipeline(
        seed_domain="notion.so",
        service_modes={"ocean": "mock", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=dry_run,
        simulate_failures=simulate_failures,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=False,
        allow_unverified_live_send=False,
        send_live=False,
    )


def test_unresolved_contacts_are_not_sent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    summary = build_pipeline(dry_run=True).run()

    assert summary.unresolved_contacts >= 1
    assert summary.mock_verified_count >= 1
    assert summary.verified_emails == 0
    assert summary.emails_ready == summary.mock_verified_count
    assert summary.emails_sent == 0


def test_dry_run_does_not_send_emails(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    summary = build_pipeline(dry_run=True).run()

    assert summary.dry_run is True
    assert summary.emails_sent == 0
    assert summary.send_decision == "dry_run"
    assert all(result["send_status"] == "dry_run" for result in summary.send_results)


def test_mock_pipeline_completes_successfully(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    summary = build_pipeline(dry_run=True).run()

    assert summary.companies_found > 0
    assert summary.contacts_found > 0
    assert summary.ocean_status["status"] == "success"


def test_simulated_failures_do_not_crash_pipeline(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    summary = build_pipeline(dry_run=True, simulate_failures=True).run()

    assert summary.contacts_found > 0
    assert summary.unresolved_contacts >= 1
    assert summary.brevo_status["status"] in {"success", "partial_success"}
    assert any(result["send_status"] == "failed" for result in summary.send_results)


def test_yes_flag_bypasses_confirmation_only_in_mock_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = OutreachPipeline(
        seed_domain="notion.so",
        service_modes={"ocean": "mock", "prospeo": "mock", "eazyreach": "mock", "brevo": "mock"},
        limit_companies=5,
        limit_contacts=20,
        max_contacts_per_company=2,
        dry_run=False,
        simulate_failures=False,
        timeout_seconds=30.0,
        max_retries=3,
        output_dir="outputs",
        assume_yes=True,
        allow_unverified_live_send=False,
        send_live=False,
    )

    summary = pipeline.run()

    assert summary.emails_sent > 0
    assert summary.send_decision == "confirmed_send"


def test_user_rejection_marks_send_as_cancelled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    summary = build_pipeline(dry_run=False).run()

    assert summary.emails_sent == 0
    assert summary.send_decision == "cancelled"
    assert summary.brevo_status["status"] == "cancelled"
    assert all(result["send_status"] == "cancelled" for result in summary.send_results)
