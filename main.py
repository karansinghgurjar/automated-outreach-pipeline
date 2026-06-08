"""CLI entrypoint for the VocalLabs outreach pipeline."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run the VocalLabs outreach pipeline in mock or mixed live modes."
    )
    parser.add_argument(
        "--domain",
        help="Seed company domain, for example notion.so or github.com.",
    )
    parser.add_argument("--test-ocean", action="store_true", help="Test Ocean API connectivity only.")
    parser.add_argument("--test-prospeo", action="store_true", help="Test Prospeo API connectivity only.")
    parser.add_argument("--test-brevo", action="store_true", help="Test Brevo API connectivity only.")
    parser.add_argument("--check-env", action="store_true", help="Check whether required env vars are present.")
    parser.add_argument(
        "--send-test-email",
        help="With --test-brevo, optionally send a test email to this address after confirmation.",
    )
    parser.add_argument(
        "--source",
        choices=["mock", "csv"],
        help="Ocean-stage source selector. Use mock or csv.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mock",
        action="store_true",
        help="Run all services in mock mode unless a specific --live-* flag overrides it.",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Run all services in live mode.",
    )
    mode_group.add_argument(
        "--fake-http",
        action="store_true",
        help="Run all services against the local fake HTTP API server.",
    )
    parser.add_argument(
        "--live-ocean",
        "--ocean-live",
        dest="live_ocean",
        action="store_true",
        help="Use live Ocean.io.",
    )
    parser.add_argument(
        "--live-prospeo",
        "--prospeo-live",
        dest="live_prospeo",
        action="store_true",
        help="Use live Prospeo.",
    )
    parser.add_argument("--live-eazyreach", action="store_true", help="Use live Eazyreach.")
    parser.add_argument(
        "--live-brevo",
        action="store_true",
        help="Select live Brevo transport. Real sending still requires --send-live.",
    )
    parser.add_argument(
        "--send-live",
        action="store_true",
        help="Enable real live sending through Brevo. Dry-run still overrides this flag.",
    )
    parser.add_argument("--mock-ocean", action="store_true", help="Force mock Ocean.io.")
    parser.add_argument("--mock-prospeo", action="store_true", help="Force mock Prospeo.")
    parser.add_argument("--mock-eazyreach", action="store_true", help="Force mock Eazyreach.")
    parser.add_argument("--mock-brevo", action="store_true", help="Force mock Brevo.")
    parser.add_argument(
        "--limit-companies",
        type=int,
        default=5,
        help="Maximum number of lookalike companies to process.",
    )
    parser.add_argument(
        "--limit-contacts",
        type=int,
        default=20,
        help="Maximum number of decision-makers to process.",
    )
    parser.add_argument(
        "--max-contacts-per-company",
        type=int,
        default=3,
        help="Maximum contacts to generate or fetch per company.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate messages and reports without confirmation or sending.",
    )
    parser.add_argument(
        "--simulate-failures",
        action="store_true",
        help="Simulate partial failures while keeping the pipeline run successful.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds for live API calls.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retry attempts for retryable operations.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Base directory for generated run reports and logs.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm only in mock mode or dry-run mode.",
    )
    parser.add_argument(
        "--allow-unverified-live-send",
        action="store_true",
        help="Allow live Brevo sending to non-provider-verified fallback emails.",
    )
    return parser


def resolve_service_modes(args: argparse.Namespace) -> dict[str, str]:
    """Resolve per-service modes from the CLI flags."""
    default_mode = "fake_http" if args.fake_http else ("live" if args.live else "mock")
    service_modes = {
        "ocean": default_mode,
        "prospeo": default_mode,
        "eazyreach": "fake_http" if args.fake_http else "skipped",
        "brevo": default_mode,
    }

    if args.live_ocean:
        service_modes["ocean"] = "live"
    if args.live_prospeo:
        service_modes["prospeo"] = "live"
    if args.live_eazyreach:
        service_modes["eazyreach"] = "live"
    if args.live_brevo:
        service_modes["brevo"] = "live"
    if args.send_live:
        service_modes["brevo"] = "live"

    if args.mock_ocean:
        service_modes["ocean"] = "mock"
    if args.mock_prospeo:
        service_modes["prospeo"] = "mock"
    if args.mock_eazyreach:
        service_modes["eazyreach"] = "mock"
    if args.mock_brevo:
        service_modes["brevo"] = "mock"

    if args.source:
        service_modes["ocean"] = args.source

    if args.live_brevo:
        args.send_live = True

    return service_modes


def main() -> None:
    """Run the pipeline with parsed CLI arguments."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.check_env:
            run_check_env()
            return
        if args.test_ocean or args.test_prospeo or args.test_brevo:
            run_api_test_commands(args)
            return

        if not args.domain:
            raise ValueError("--domain is required unless you are running an API test command.")

        from app.pipeline import OutreachPipeline

        pipeline = OutreachPipeline(
            seed_domain=args.domain,
            service_modes=resolve_service_modes(args),
            limit_companies=args.limit_companies,
            limit_contacts=args.limit_contacts,
            max_contacts_per_company=args.max_contacts_per_company,
            dry_run=args.dry_run,
            simulate_failures=args.simulate_failures,
            timeout_seconds=args.timeout,
            max_retries=args.max_retries,
            output_dir=args.output_dir,
            assume_yes=args.yes,
            allow_unverified_live_send=args.allow_unverified_live_send,
            send_live=args.send_live,
        )
        pipeline.run()
    except ValueError as exc:
        print(f"Input error: {exc}")
        sys.exit(1)
    except NotImplementedError as exc:
        print(f"Requested mode is wired but not implemented yet: {exc}")
        sys.exit(1)


def run_api_test_commands(args: argparse.Namespace) -> None:
    test_flags = [args.test_ocean, args.test_prospeo, args.test_brevo]
    if sum(1 for enabled in test_flags if enabled) != 1:
        raise ValueError("Choose exactly one of --test-ocean, --test-prospeo, or --test-brevo.")
    if args.send_test_email and not args.test_brevo:
        raise ValueError("--send-test-email can only be used together with --test-brevo.")

    from app.services.brevo import BrevoService
    from app.config import get_settings
    from app.services.ocean import OceanService
    from app.services.prospeo import ProspeoService
    settings = get_settings()

    if args.test_ocean:
        result = OceanService(mode="mock").test_connection(timeout_seconds=args.timeout)
        print(result["message"])
        payload = result.get("payload")
        if isinstance(payload, dict):
            daily_limit = payload.get("dailyLimitRateLeft")
            if daily_limit is not None:
                print(f"Daily limit remaining: {daily_limit}")
        return

    if args.test_prospeo:
        result = ProspeoService(mode="mock", timeout_seconds=args.timeout, max_retries=args.max_retries).test_connection()
        print(result["message"])
        if result.get("current_plan"):
            print(f"Current plan: {result['current_plan']}")
        if result.get("remaining_credits") is not None:
            print(f"Remaining credits: {result['remaining_credits']}")
        if result.get("used_credits") is not None:
            print(f"Used credits: {result['used_credits']}")
        return

    brevo = BrevoService(
        mode="live",
        sender_email=settings.brevo_sender_email,
        sender_name=settings.brevo_sender_name,
        api_key=settings.brevo_api_key,
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
    )
    result = brevo.test_connection()
    print(result["message"])
    print(f"Sender email configured: {result['sender_email_configured']}")
    print(f"Sender name configured: {result['sender_name_configured']}")
    if args.send_test_email:
        response = input(
            f"Send a Brevo test email to {args.send_test_email}? [y/N]: "
        ).strip().lower()
        if response != "y":
            print("Brevo test email cancelled.")
            return
        send_result = brevo.send_test_email(args.send_test_email)
        print(f"Brevo test email send status: {send_result.send_status}")
        if send_result.provider_message_id:
            print(f"Provider message id: {send_result.provider_message_id}")
        if send_result.failure_reason:
            print(f"Failure reason: {send_result.failure_reason}")


def run_check_env() -> None:
    from app.config import get_env_presence

    for key, status in get_env_presence().items():
        print(f"{key}: {status}")


if __name__ == "__main__":
    main()
