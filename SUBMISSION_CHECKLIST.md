# Submission Checklist

- `.env` is not committed
- `.env.example` contains placeholders only
- `python -m pytest` passes
- CSV dry-run works
- Prospeo live dry-run works if `PROSPEO_API_KEY` is configured
- Brevo live only runs with `--send-live`
- safety checkpoint has been tested
- reports and logs are generated
- README is updated
- no Eazyreach key is required
- Ocean fallback is documented
- live send is not used for submission unless tested only with owned inboxes
