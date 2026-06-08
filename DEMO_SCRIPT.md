# 4-Minute Demo Script

## 1. Assignment Summary

This project is a command-line outreach pipeline for the Vocallabs/Subspace SDE assignment. It starts from a seed company domain, finds similar companies, finds senior contacts, and prepares outreach safely.

## 2. Official Eazyreach Update

The original PDF included Eazyreach, but the official update said Eazyreach credits would not be provided. Because of that, the live pipeline is now:

`Ocean fallback -> Prospeo -> Brevo`

## 3. Show The CLI

```powershell
python main.py --help
```

Call out:

- `--source csv`
- `--prospeo-live`
- `--send-live`
- `--check-env`
- `--test-ocean`, `--test-prospeo`, `--test-brevo`

## 4. Run The Safe Demo Path

```powershell
python main.py --domain openai.com --source csv --dry-run
```

Explain:

- Ocean uses the CSV fallback
- Eazyreach is skipped by design
- Brevo stays in dry-run mode
- reports and logs are generated automatically

## 5. Run Live Prospeo Dry-Run

```powershell
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```

Explain:

- live Prospeo is the contact and email source
- limits keep credit usage controlled
- dry-run avoids any live sending

## 6. Show The Artifacts

Open:

- `outputs/runs/<timestamp>_summary.json`
- `outputs/runs/<timestamp>_contacts.csv`
- `outputs/logs/<timestamp>_pipeline.log`

Point out:

- companies found
- contacts found
- emails found
- contacts without email
- duplicate counts
- send results

## 7. Explain Live Send Safety

Mention:

- live send only happens with `--send-live`
- `--dry-run` always overrides it
- the safety checkpoint defaults to No
- pressing Enter does not send

## 8. Explain Modular Services

- `OceanService` supports fallback modes
- `ProspeoService` handles live people and email lookup
- `BrevoService` is isolated for safe send logic
- `OutreachPipeline` orchestrates the stages and reporting

## 9. Next Steps

- replace Ocean fallback with true live Ocean access if available
- test live Brevo only with owned inboxes
- add persistence or dashboard if the project were extended further
