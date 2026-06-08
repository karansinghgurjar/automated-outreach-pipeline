# Ocean Fallback Note

Ocean live access is not required for the submission-ready version of this project.

If Ocean live access is missing, blocked, or returns:

- `HTTP 403`
- missing key
- account permission errors

use the CSV fallback:

```powershell
python main.py --domain openai.com --source csv --prospeo-live --limit-companies 2 --max-contacts-per-company 2 --dry-run
```

Why this is acceptable:

- the project still preserves the Ocean service boundary
- the assignment can still be demonstrated end to end
- the live Prospeo and Brevo safety logic can still be explained clearly
- only `OceanService` needs to change later if live Ocean access is restored
