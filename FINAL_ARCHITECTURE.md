# Final Architecture

## Layers

- CLI layer: [main.py](C:\Users\hp5cd\Documents\subspace_Assingemnt\vocallabs-outreach-pipeline\main.py)
- config layer: [app/config.py](C:\Users\hp5cd\Documents\subspace_Assingemnt\vocallabs-outreach-pipeline\app\config.py)
- pipeline orchestrator: [app/pipeline.py](C:\Users\hp5cd\Documents\subspace_Assingemnt\vocallabs-outreach-pipeline\app\pipeline.py)
- service layer: `app/services/`
- model layer: [app/models.py](C:\Users\hp5cd\Documents\subspace_Assingemnt\vocallabs-outreach-pipeline\app\models.py)
- utility layer: `app/utils/`
- outputs layer: `outputs/runs/` and `outputs/logs/`

## Updated Live Flow

The original assignment included Eazyreach, but the official update replaced that live dependency with Prospeo.

Current live/demo pipeline:

`Ocean / Ocean fallback -> Prospeo -> Brevo`

## ASCII Diagram

```text
User Domain
    |
    v
CLI
    |
    v
Pipeline Orchestrator
    |
    +--> OceanService
    |       - mock
    |       - csv fallback
    |       - live placeholder
    |
    +--> ProspeoService
    |       - mock
    |       - live search
    |       - live enrich for email
    |
    +--> EazyreachService
    |       - optional / deprecated / skipped by default
    |
    +--> BrevoService
    |       - mock
    |       - live send with strict safety
    |
    v
Reports + Logs
```
