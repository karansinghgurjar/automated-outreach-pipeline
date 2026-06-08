# Automated Outreach Pipeline

A Python CLI project for the Vocallabs/Subspace SDE assignment.

The pipeline takes one seed company domain and runs an automated outreach workflow:

```text
Ocean/Ocean fallback -> Prospeo -> Brevo
```

The original assignment included Eazyreach, but the official update allowed Prospeo to replace Eazyreach for finding people, LinkedIn URLs, and email IDs.

## Quick Demo

```bash
python main.py --domain openai.com --source csv --dry-run
```

This runs the safe demo path:

`CSV Ocean fallback -> Prospeo mock/live-ready -> Brevo dry-run`

No live emails are sent.

For live Prospeo dry-run:

```bash
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```

## 1. Project Overview

This project automates a lightweight outbound workflow from a single seed domain. It finds similar companies, finds senior contacts, prepares outreach data, and can hand verified recipients to Brevo. The default path is intentionally safe for demos and interviews.

## 2. Updated Pipeline

Original PDF pipeline:

```text
Ocean.io -> Prospeo -> Eazyreach -> Brevo
```

Official updated live/demo path:

```text
Ocean/Ocean fallback -> Prospeo -> Brevo
```

Eazyreach remains in the codebase only for architectural completeness and is skipped by default.

## 3. Features

- Single-command CLI pipeline execution
- Ocean CSV fallback and mock mode
- Live-ready Prospeo integration
- Brevo dry-run by default
- Guarded live sending through `--send-live`
- Safety checkpoint before live email sending
- JSON summary, CSV contact export, and pipeline logs
- API connectivity checks with `--test-ocean`, `--test-prospeo`, and `--test-brevo`
- Graceful error handling and retry/backoff for live APIs
- Automated test suite with `python -m pytest`

## 4. Architecture

High-level flow:

```text
Seed Domain
  -> OceanService (csv/mock/live placeholder)
  -> ProspeoService (mock/live)
  -> BrevoService (mock/dry-run/live)
  -> JSON summary + CSV contacts + log file
```

Key modules:

- `main.py` handles CLI parsing and preflight commands.
- `app/config.py` loads `.env` and shared settings.
- `app/pipeline.py` orchestrates the end-to-end workflow.
- `app/services/` isolates provider-specific logic.
- `app/models.py` defines the shared data structures between stages.

## 5. Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 6. Environment Variables

Create a local `.env` file next to [main.py](C:\Users\hp5cd\Documents\subspace_Assingemnt\vocallabs-outreach-pipeline\main.py):

```env
OCEAN_API_KEY=
PROSPEO_API_KEY=
BREVO_API_KEY=
BREVO_SENDER_EMAIL=karan@karanadhanaoutreach.xyz
BREVO_SENDER_NAME=Karan Singh Gurjar
```

Do not commit `.env`.

Check env presence safely:

```powershell
python main.py --check-env
```

## 7. Commands

Provider connectivity checks:

```powershell
python main.py --test-ocean
python main.py --test-prospeo
python main.py --test-brevo
```

CSV fallback demo:

```powershell
python main.py --domain openai.com --source csv --dry-run
```

Input validation:

```powershell
python main.py --domain invalid_domain --source csv --dry-run
```

Run tests:

```powershell
python -m pytest
```

## 8. Safe Demo Path

Use this for submission and interview demos:

```powershell
python main.py --domain openai.com --source csv --dry-run
```

This path:

- does not require Ocean live access
- does not require Brevo live sending
- skips Eazyreach
- writes reports and logs automatically

## 9. Live Prospeo Dry Run

Use this when `PROSPEO_API_KEY` is configured:

```powershell
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```

Live Prospeo behavior:

- searches senior contacts first
- enriches contacts for email where available
- respects `--limit-companies`, `--limit-contacts`, and `--max-contacts-per-company`
- uses conservative defaults to avoid excessive credit usage

## 10. Brevo Live Sending Safety

- Live sending is off by default.
- `--send-live` is required before any real email can be sent.
- `--dry-run` always overrides `--send-live`.
- Live Brevo requires `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and `BREVO_SENDER_NAME`.
- The confirmation checkpoint defaults to `No`.
- Pressing Enter does not send.
- One failed email does not crash the full run.

Test live Brevo only with your own email address or controlled test contacts first.

## 11. Outputs

Each run creates:

- `outputs/runs/<timestamp>_summary.json`
- `outputs/runs/<timestamp>_contacts.csv`
- `outputs/logs/<timestamp>_pipeline.log`

End-of-run output includes:

- companies found
- contacts found
- emails found
- contacts without email
- duplicate contacts removed
- duplicate emails removed
- emails ready
- emails sent
- emails failed
- report file paths

## 12. Testing

Run the full suite with:

```powershell
python -m pytest
```

The test suite covers:

- env safety
- CSV fallback behavior
- invalid domain handling
- Prospeo live preflight
- Brevo live-send guards
- deduplication
- report generation
- dry-run safety

## 13. Troubleshooting

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
  Contacts without usable email are skipped before Brevo.

## 14. Assignment Notes

- The original assignment included Eazyreach.
- The official update allowed Prospeo to replace Eazyreach for people, LinkedIn URLs, and email IDs.
- Because Ocean live access can fail with account permission issues, the project includes CSV and mock Ocean fallback modes.
- The safest submission-ready command is:

```powershell
python main.py --domain openai.com --source csv --dry-run
```
