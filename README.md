# Automated Outreach Pipeline

This project is a command-line automated outreach pipeline for the Vocallabs/Subspace SDE assignment.

Original PDF pipeline:
`Ocean.io -> Prospeo -> Eazyreach -> Brevo`

Official update:
Subspace/Vocallabs later said Eazyreach credits were unavailable, and candidates should use Prospeo itself to find people, LinkedIn URLs, and email IDs.

Current live target:
`Ocean / Ocean fallback -> Prospeo -> Brevo`

## Project Purpose

- Find lookalike companies from one seed domain.
- Find senior decision-makers for those companies.
- Use Prospeo as the live contact and email source.
- Prepare or send outreach emails with Brevo.
- Generate JSON, CSV, and log outputs for every run.

## Why Eazyreach Is Skipped

The original assignment included Eazyreach, but the official requirement changed. This project keeps the `EazyreachService` code only for architectural completeness. The normal live/demo path skips it entirely.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a local `.env` file next to [main.py](C:\Users\hp5cd\Documents\subspace_Assingemnt\vocallabs-outreach-pipeline\main.py):

```env
OCEAN_API_KEY=
PROSPEO_API_KEY=
BREVO_API_KEY=
BREVO_SENDER_EMAIL=karan@karanadhanaoutreach.xyz
BREVO_SENDER_NAME=Karan Singh Gurjar
```

Do not commit `.env`. Do not paste API keys into chat.

## Safe Commands

Check whether env vars are present:

```powershell
python main.py --check-env
```

Test provider connectivity:

```powershell
python main.py --test-ocean
python main.py --test-prospeo
python main.py --test-brevo
```

CSV fallback dry-run:

```powershell
python main.py --domain openai.com --source csv --dry-run
```

Live Prospeo dry-run with conservative limits:

```powershell
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```

Validate input handling:

```powershell
python main.py --domain invalid_domain --source csv --dry-run
```

Run tests:

```powershell
python -m pytest
```

## CLI Notes

- `--mock` keeps the demo path fully local and safe.
- `--source csv` uses the bundled `data/seed_companies.csv` fallback and does not require `OCEAN_API_KEY`.
- `--prospeo-live` and `--live-prospeo` are aliases.
- `--ocean-live` and `--live-ocean` are aliases.
- `--send-live` is the only flag that allows real Brevo sending.
- `--dry-run` always overrides `--send-live`.

## Prospeo Live Behavior

Prospeo live mode:

- searches senior contacts first
- enriches contacts to retrieve email where available
- respects `--limit-companies`, `--limit-contacts`, and `--max-contacts-per-company`
- retries 429/5xx/timeout cases with backoff
- continues when one company fails

Conservative defaults:

- `--limit-contacts` defaults to `20`
- `--max-contacts-per-company` defaults to `3`

## Brevo Live Safety

- Live sending is off by default.
- `--send-live` is required before any real email can be sent.
- The safety checkpoint defaults to No.
- Pressing Enter does not send.
- One failed email does not crash the run.

Warning:
Test live Brevo only with your own email address or dedicated test contacts first.

## Ocean Fallback

Ocean live access is optional for submission. If Ocean API access is missing or returns `403`, use:

```powershell
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```

CSV fallback rules:

- validates domains
- deduplicates domains
- respects `--limit-companies`
- fails cleanly if CSV is missing, empty, or malformed

## Outputs

Each run creates:

- `outputs/runs/<timestamp>_summary.json`
- `outputs/runs/<timestamp>_contacts.csv`
- `outputs/logs/<timestamp>_pipeline.log`

End-of-run output shows:

- companies found
- contacts found
- emails found
- contacts without email
- duplicate contacts removed
- duplicate emails removed
- emails ready
- emails sent
- emails failed
- JSON summary path
- CSV contacts path
- log path

## Troubleshooting

- `Missing PROSPEO_API_KEY in .env`
  Add the key to your local `.env`.
- `Prospeo API: FAILED - invalid API key`
  The key is present but not accepted by Prospeo.
- `Ocean API: FAILED - HTTP 403... Use --source csv until Ocean API access is resolved.`
  Ocean access exists but does not have permission for the tested endpoint.
- `Brevo API: FAILED - authentication error (HTTP 401)`
  The Brevo key is not valid for account access.
- No contacts found
  The run still completes and writes reports.
- No emails found
  Prospeo can return people without usable emails; those contacts are skipped before Brevo.

## Submission Demo Command

Even if Ocean live is unavailable, this is the safest submission-ready command:

```powershell
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```
