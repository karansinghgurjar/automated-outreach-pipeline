# Final Test Commands

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Verification Commands

```powershell
python main.py --help
python main.py --check-env
python main.py --test-prospeo
python main.py --test-brevo
python main.py --test-ocean
python main.py --domain openai.com --source csv --dry-run
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
python main.py --domain invalid_domain --source csv --dry-run
python -m pytest
```

## Notes

- Use `python -m pytest` instead of `pytest` if `pytest` is not on PATH.
- Use the CSV fallback for submission demos if Ocean live access is unavailable.
- Do not use `--send-live` unless you are testing only with your own inboxes.
