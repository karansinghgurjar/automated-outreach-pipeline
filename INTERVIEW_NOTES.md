# Interview Notes

## Design Decisions

- Mock mode first:
  I built mock mode first so the pipeline architecture, reports, and safety controls can always be demonstrated even if external APIs or credits are unavailable.
- Modular services:
  Each provider is isolated in its own service class so integrations can change without rewriting orchestration logic.
- Pipeline orchestrator:
  One orchestrator coordinates stage order, logging, retries, deduplication, summary creation, and output files.
- Safety checkpoint:
  Sending is gated behind a confirmation step that defaults to No.
- Deduplication:
  Duplicate companies, contacts, and emails are removed before downstream stages can amplify bad data.
- Retry/backoff:
  Retry behavior is centralized so temporary provider issues can be handled consistently.
- Reports/logs:
  Every run produces audit artifacts that make debugging and demoing easier.
- Partial failure handling:
  One bad company, contact, or send result should not crash the entire run.

## Why modular services?

Each provider has its own service class so the orchestration logic stays clean. That separation makes the code easier to test, easier to swap between mock and live implementations, and safer to change when one provider API evolves.

## Why mock mode first?

Mock mode gives me a reliable demo path and lets me validate architecture, control flow, reports, and safety features before depending on API credits, network stability, or account setup. It is a professional fallback, not a shortcut.

## How do you handle rate limits?

I added a reusable retry framework with configurable max attempts, initial delay, backoff factor, and retryable status codes. For live Brevo, retryable server and rate-limit responses can be retried with exponential backoff.

## How do you handle partial failures?

Each major stage is wrapped in `try/except`, and every stage returns a structured status object with counts and an optional error message. Per-item failures are logged and converted into unresolved contacts or failed send results so one bad record does not crash the full run.

## How do you prevent duplicate emails?

Before the send stage, the pipeline normalizes emails to lowercase and removes duplicates. The run summary tracks `duplicates_removed` so the behavior is visible and auditable.

## How do you avoid accidental email blasts?

There is a safety checkpoint before non-dry-run sending. It shows counts and sample recipients, then asks for confirmation with a default answer of No. Dry-run mode bypasses sending entirely.

## How would you scale this?

I would move stage execution onto a queue, batch requests per provider, persist results in a database, add idempotency keys for sends, and instrument metrics around stage latency, resolution rates, and send outcomes.

## What would you improve next?

- Implement live Prospeo, Ocean.io, and Eazyreach integrations.
- Add provider-specific pagination handling and richer retries.
- Add Brevo sandbox-mode support for safer live integration testing.
- Persist run history in a database instead of only files.
- Add CI to run tests automatically on every push.
