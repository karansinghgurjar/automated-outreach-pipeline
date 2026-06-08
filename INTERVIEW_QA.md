# Interview Q&A

## What does this project do?

It takes a seed company domain, finds similar companies, finds senior contacts for those companies, and prepares outreach emails in a safe, auditable CLI pipeline.

## Why is Eazyreach skipped?

The original PDF included Eazyreach, but Subspace/Vocallabs later said Eazyreach credits were unavailable and candidates should use Prospeo itself to find people, LinkedIn URLs, and email IDs. So the live pipeline became Ocean/Ocean fallback -> Prospeo -> Brevo.

## Did you remove Eazyreach completely?

No. I kept it optional and deprecated for architectural completeness, but the live/demo path does not depend on it.

## What happens if Ocean API fails?

The project does not depend on Ocean live access for the demo path. If Ocean access is unavailable or returns a permission error, the CLI can use the CSV fallback with `--source csv`.

## Why CSV fallback?

It keeps the pipeline demoable even if Ocean live access is blocked or delayed. That lets the architecture, reporting, and safety flows still be shown end to end.

## How do you handle API keys?

Keys are loaded from `.env` through one shared config layer. They are never hardcoded, never printed, never logged, and `.env` is gitignored.

## How do you handle rate limits?

Retryable HTTP failures such as 429 and 5xx are routed through a retry helper with backoff and timeout controls.

## How do you control Prospeo credits?

Live Prospeo uses conservative defaults and supports `--limit-companies`, `--limit-contacts`, and `--max-contacts-per-company` so the demo cannot accidentally consume too many credits.

## How do you prevent duplicate emails?

The pipeline normalizes emails to lowercase and deduplicates them before the Brevo stage. If no email exists, it falls back to LinkedIn URL identity for contact deduplication.

## How do you prevent accidental email blasts?

Live send is disabled by default. Real sends require `--send-live`, then a confirmation prompt that defaults to No. Pressing Enter does not send.

## What if Prospeo returns no emails?

The run still completes. Contacts without email are counted, written to the reports, and skipped before Brevo.

## What if Brevo fails for one email?

That single email is marked failed in the send results, the failure reason is recorded, and the rest of the send run continues.

## How would you scale this?

I would add persistence, queue-based execution, resumable run state, and batched provider workflows with metrics and alerting.

## What would you improve next?

I would add true Ocean live integration if access is available, improve provider-specific observability, and add a lightweight dashboard for run history and send review.
