"""
Webhook API — lets external monitoring tools (Datadog, PagerDuty, etc.)
POST incidents directly instead of using the Streamlit UI.

Run locally:  uvicorn api.webhook:app --port 8000 --reload
In Docker:    see docker-compose.yml (api service)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agents.state import create_initial_state
from db.history import save_incident, init_db
from graph.workflow import app as pipeline_app
from notifications.slack import notify as slack_notify
from notifications.github_pr import create_pr

init_db()

app = FastAPI(
    title="Incident Response Webhook",
    description="POST an incident payload to trigger the full AI pipeline.",
    version="1.0.0",
)

_API_KEY = os.getenv("WEBHOOK_API_KEY", "")


def _check_auth(x_api_key: str) -> None:
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key header.")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IncidentPayload(BaseModel):
    logs: str = Field(..., description="Raw error logs or stack trace text.")
    complaints: list[str] = Field(..., description="One complaint message per list item.")
    source: str = Field("webhook", description="Origin system identifier (e.g. 'datadog', 'pagerduty').")


class IncidentResult(BaseModel):
    incident_id: int
    severity: str
    status: str
    correlated_error: str
    root_cause: str
    tests_passed: bool
    escalate_to_human: bool
    affected_customers: list[str]
    patch_explanation: str
    run_time_seconds: float
    slack_notified: bool
    github_pr_url: str | None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/incident", response_model=IncidentResult)
def receive_incident(
    payload: IncidentPayload,
    x_api_key: str = Header(default=""),
):
    """
    Trigger the full incident response pipeline.

    The pipeline runs synchronously and returns when complete.
    For long-running incidents this may take 30–120 seconds.

    Authentication: set WEBHOOK_API_KEY in .env and pass it as
    the `X-Api-Key` request header.  If WEBHOOK_API_KEY is empty,
    authentication is disabled (dev mode).
    """
    _check_auth(x_api_key)

    start = time.time()
    state = create_initial_state(complaints=payload.complaints, logs=payload.logs)

    try:
        result = pipeline_app.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    run_time = time.time() - start
    incident_id = save_incident(result, run_time)
    slack_sent = slack_notify(result, run_time, incident_id)
    pr_url = create_pr(result, incident_id)

    return IncidentResult(
        incident_id=incident_id,
        severity=result.get("severity", "P2"),
        status=result.get("status", ""),
        correlated_error=result.get("correlated_error", ""),
        root_cause=result.get("root_cause", ""),
        tests_passed=bool(result.get("tests_passed")),
        escalate_to_human=bool(result.get("escalate_to_human")),
        affected_customers=result.get("affected_customers", []),
        patch_explanation=result.get("patch_explanation", ""),
        run_time_seconds=round(run_time, 1),
        slack_notified=slack_sent,
        github_pr_url=pr_url,
    )
