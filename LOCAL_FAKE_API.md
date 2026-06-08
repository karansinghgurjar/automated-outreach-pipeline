# Local Fake API

This project supports a local fake HTTP mode so the pipeline can exercise real request and response behavior without external API keys.

## Install

```powershell
pip install -r requirements.txt
```

## Start the fake API server

```powershell
python fake_api_server.py
```

The default base URL is:

```text
http://127.0.0.1:8000
```

## Run the pipeline against the fake API

```powershell
python main.py --domain notion.so --fake-http --dry-run
```

## Environment

Set in `.env` if needed:

```env
FAKE_API_BASE_URL=http://127.0.0.1:8000
```

Optional failure mode for testing:

```env
FAKE_API_FAIL_MODE=rate_limit
FAKE_API_FAIL_MODE=server
FAKE_API_FAIL_MODE=empty
```

## What it simulates

- `POST /ocean/lookalikes`
- `POST /prospeo/decision-makers`
- `POST /eazyreach/resolve`
- `POST /brevo/send`

## Example workflow

```powershell
python fake_api_server.py
python main.py --domain notion.so --fake-http --dry-run
```
