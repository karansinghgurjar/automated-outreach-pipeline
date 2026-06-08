"""Local fake API server for HTTP-level integration testing."""

from __future__ import annotations

from fastapi import FastAPI, Header, Query
from pydantic import BaseModel
import uvicorn


app = FastAPI(title="VocalLabs Fake API Server")


class OceanRequest(BaseModel):
    domain: str


class ProspeoRequest(BaseModel):
    domains: list[str]


class ContactPayload(BaseModel):
    name: str
    title: str
    company_domain: str
    linkedin_url: str | None = None


class EazyreachRequest(BaseModel):
    contacts: list[ContactPayload]


class EmailPayload(BaseModel):
    email: str
    subject: str | None = None
    body: str | None = None


class BrevoRequest(BaseModel):
    emails: list[EmailPayload]
    dry_run: bool = False


def _resolve_fail_mode(
    fail: str | None = Query(default=None),
    x_fake_fail: str | None = Header(default=None),
) -> str | None:
    return fail or x_fake_fail


def _failure_response(fail_mode: str | None, empty_payload: dict) -> tuple[int, dict] | None:
    if fail_mode == "rate_limit":
        return 429, {"error": "rate_limited"}
    if fail_mode == "server":
        return 500, {"error": "server_error"}
    if fail_mode == "empty":
        return 200, empty_payload
    return None


@app.post("/ocean/lookalikes")
def ocean_lookalikes(
    payload: OceanRequest,
    fail: str | None = Query(default=None),
    x_fake_fail: str | None = Header(default=None),
) -> dict:
    fail_mode = _resolve_fail_mode(fail, x_fake_fail)
    failure = _failure_response(fail_mode, {"companies": []})
    if failure:
        status_code, body = failure
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status_code, content=body)

    return {
        "companies": [
            {"name": "Airtable", "domain": "airtable.com"},
            {"name": "ClickUp", "domain": "clickup.com"},
            {"name": "Monday", "domain": "monday.com"},
        ]
    }


@app.post("/prospeo/decision-makers")
def prospeo_decision_makers(
    payload: ProspeoRequest,
    fail: str | None = Query(default=None),
    x_fake_fail: str | None = Header(default=None),
) -> dict:
    fail_mode = _resolve_fail_mode(fail, x_fake_fail)
    failure = _failure_response(fail_mode, {"contacts": []})
    if failure:
        status_code, body = failure
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status_code, content=body)

    contacts = []
    for domain in payload.domains:
        contacts.append(
            {
                "name": "Sarah Chen",
                "title": "VP Growth",
                "company_domain": domain,
                "linkedin_url": f"https://linkedin.com/in/sarah-chen-{domain.split('.')[0]}",
            }
        )

    return {"contacts": contacts}


@app.post("/eazyreach/resolve")
def eazyreach_resolve(
    payload: EazyreachRequest,
    fail: str | None = Query(default=None),
    x_fake_fail: str | None = Header(default=None),
) -> dict:
    fail_mode = _resolve_fail_mode(fail, x_fake_fail)
    failure = _failure_response(
        fail_mode,
        {"verified_contacts": [], "unresolved_contacts": []},
    )
    if failure:
        status_code, body = failure
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status_code, content=body)

    verified_contacts = []
    unresolved_contacts = []
    for contact in payload.contacts:
        if not contact.linkedin_url:
            unresolved_contacts.append(
                {
                    "name": contact.name,
                    "title": contact.title,
                    "company_domain": contact.company_domain,
                    "linkedin_url": contact.linkedin_url,
                    "email": None,
                    "verification_status": "unresolved",
                    "failure_reason": "Missing LinkedIn URL",
                }
            )
            continue

        email_prefix = contact.name.lower().replace(" ", ".")
        verified_contacts.append(
            {
                "name": contact.name,
                "title": contact.title,
                "company_domain": contact.company_domain,
                "linkedin_url": contact.linkedin_url,
                "email": f"{email_prefix}@{contact.company_domain}",
                "verification_status": "verified",
            }
        )

    return {
        "verified_contacts": verified_contacts,
        "unresolved_contacts": unresolved_contacts,
    }


@app.post("/brevo/send")
def brevo_send(
    payload: BrevoRequest,
    fail: str | None = Query(default=None),
    x_fake_fail: str | None = Header(default=None),
) -> dict:
    fail_mode = _resolve_fail_mode(fail, x_fake_fail)
    failure = _failure_response(fail_mode, {"results": []})
    if failure:
        status_code, body = failure
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status_code, content=body)

    results = []
    for index, email in enumerate(payload.emails, start=1):
        results.append(
            {
                "email": email.email,
                "send_status": "dry_run" if payload.dry_run else "sent",
                "provider_message_id": f"fake_msg_{index}",
            }
        )

    return {"results": results}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
