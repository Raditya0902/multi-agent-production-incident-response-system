# PROJECT CONTEXT — Multi-Agent Production Incident Response System

> **How to use this file:** Paste the entire contents into a new Claude conversation.
> Claude will then have complete context about this project and can help you with
> anything — debugging, feature additions, explaining code, architecture questions, etc.

---

## What This Project Is

A fully autonomous AI pipeline that handles production software incidents end-to-end. When something breaks in production, you paste the error logs and customer complaints into a Streamlit dashboard and click **Run**. Within 90 seconds, the system has diagnosed the root cause, written a code fix, tested it in a sandbox, drafted personalized replies to every affected customer, sent a Slack notification, and opened a GitHub PR — all with a human approval gate before any code is touched.

**GitHub repo:** `https://github.com/Raditya0902/multi-agent-production-incident-response-system`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (`StateGraph`) |
| LLM | Groq API — `llama-3.3-70b-versatile` (default) |
| RAG | ChromaDB + `sentence-transformers/all-MiniLM-L6-v2` |
| Frontend | Streamlit |
| Webhook API | FastAPI + Uvicorn |
| Notifications | slack-sdk (bot token or webhook URL) |
| GitHub integration | PyGithub |
| Analytics charts | Plotly Express |
| Persistence | SQLite (stdlib `sqlite3`) |
| Testing | pytest |
| Containerization | Docker + Docker Compose |

---

## Project Directory Structure

```
agents/
  __init__.py              # Lazy LLM singleton with exponential backoff retry
  state.py                 # IncidentState TypedDict + create_initial_state()
  correlation_agent.py     # Links errors to customer names from logs/complaints
  severity_agent.py        # Classifies P0 / P1 / P2 with reasoning
  root_cause_agent.py      # RAG-augmented root cause diagnosis
  fix_generator_agent.py   # Generates code patches in delimited format
  execution_agent.py       # Writes + runs pytest harness in sandbox subprocess
  critic_agent.py          # Analyzes test failures, guides next fix attempt
  customer_response_agent.py   # Drafts personalized replies (all in one LLM call)
  incident_report_agent.py     # Generates Markdown postmortem

graph/
  workflow.py              # Three compiled LangGraph graphs: phase1_app, phase2_app, app

rag/
  vectorstore.py           # ChromaDB wrapper — retrieve_context(), add_documents()
  ingestion.py             # Ingest past_incidents/*.md — run once before starting
  past_incidents/          # 4 Markdown knowledge-base files (IndexError, KeyError, Timeout, AttributeError)
  chroma_db/               # Persisted vector index (auto-created)

app/                       # Buggy sample source files (one per test scenario)
  data_processing.py       # IndexError at line 42
  payment_service.py       # KeyError at line 87
  api_gateway.py           # KeyError at line 23
  notification_service.py  # AttributeError at line 78
  order_service.py         # IndexError at line 55
  analytics_service.py     # ZeroDivisionError at line 91
  database_service.py      # TimeoutError at line 134

db/
  history.py               # SQLite CRUD — save_incident(), list_incidents(), get_analytics_data()

notifications/
  slack.py                 # Block Kit messages via bot token or webhook URL
  github_pr.py             # Branch, commit, and PR creation via PyGithub

api/
  webhook.py               # FastAPI webhook — POST /webhook/incident

frontend/
  app.py                   # Main Streamlit app (5-phase HITL state machine)
  pages/
    1_History.py           # Incident history with severity filter + postmortem download
    2_Analytics.py         # Plotly charts: severity, MTTR, retries, outcome matrix

sandbox/
  Dockerfile               # Isolated container for code execution (optional)

tests/
  conftest.py
  test_agents.py           # Patch parser, router logic, RAG, execution sandbox
  test_history.py          # SQLite CRUD with temp DB isolation
  test_slack.py            # Block builders and transport layer (21 tests)
  test_github_pr.py        # Branch naming, patch application, PR body (22 tests)

data/
  sample_logs/             # indexerror_log.txt, keyerror_log.txt, timeout_log.txt
  sample_complaints/       # complaints.json

Dockerfile                 # App Docker image (python:3.11-slim, CPU-only torch)
docker-compose.yml         # Streamlit (8501) + FastAPI webhook (8000)
entrypoint.sh              # RAG ingestion → Streamlit start
requirements.txt
.env.example
test_cases.txt             # 7 ready-to-paste test scenarios
```

---

## The State Schema (`agents/state.py`)

Every agent reads from and writes to a single shared `IncidentState` TypedDict. Each agent returns only the fields it updates — LangGraph merges these into the state automatically.

```python
class IncidentState(TypedDict):
    # Inputs
    raw_complaints: List[str]    # one complaint message per list item
    raw_logs: str                # raw error logs / stack trace

    # Correlation Agent output
    correlated_error: str        # 1-2 sentence error summary
    affected_customers: List[str] # ["Alice Johnson", "Bob Martinez"]

    # Severity Agent output
    severity: str                # "P0" | "P1" | "P2"
    severity_reason: str         # one-sentence justification

    # Root Cause Agent output
    root_cause: str              # detailed diagnosis
    relevant_files: List[str]    # ["data_processing.py", ...]

    # Fix Generator output
    code_patch: str              # full delimited patch text
    patch_explanation: str       # extracted one-line explanation

    # Execution Agent output
    test_results: str            # full pytest stdout+stderr
    tests_passed: bool

    # Critic Agent / retry loop
    retry_count: int             # incremented by execution_agent each attempt
    critic_feedback: str         # structured WHAT FAILED / WHY / NEXT ATTEMPT MUST

    # Downstream outputs
    customer_replies: List[str]  # ["To: Alice\n\n...", "To: Bob\n\n..."]
    postmortem_report: str       # full Markdown postmortem

    # Control flags
    escalate_to_human: bool      # True when max retries exhausted
    status: str                  # "started" | "correlation_complete" | ... | "complete" | "escalated"
```

---

## Pipeline Architecture — The Two-Phase Split

The pipeline is split into **two separate compiled LangGraph graphs** to support the human approval gate without needing LangGraph's persistent checkpointers.

```
Phase 1 (Diagnosis)       Human Gate         Phase 2 (Execution)
─────────────────────     ──────────         ──────────────────────────────────────
Correlation Agent    ─┐
Severity Agent        │   Approve ──────►   Execution Agent ─┬─ (pass) ──► Customer Response Agent
Root Cause Agent      ├── Patch               │               │                    │
Fix Generator Agent  ─┘   Review    Reject ──► Fix Generator  └─ (fail) ──► Critic Agent ──► Fix Generator
                                   ──────►   (direct call,           (retry loop, up to MAX_RETRY_ATTEMPTS)
                                             no graph re-run)
```

**How it works in code:**

- `phase1_app = build_phase1()` — compiled graph: correlation → severity → root_cause → fix_generator → END
- `phase2_app = build_phase2()` — compiled graph: execution → [critic → fix_generator loop] → customer_response → incident_report → END (or → escalate → END)
- `app = build_workflow()` — full no-HITL graph used by tests and the webhook API

**The human gate in `frontend/app.py`:**

1. Phase 1 streams via `phase1_app.stream(state)`, result saved to `st.session_state["hitl_state"]`
2. UI switches to "awaiting_approval" — shows the patch + Approve / Reject buttons
3. **Approve:** sets `hitl_phase = "running_phase2"`, passes saved state directly into `phase2_app.stream(state)`
4. **Reject:** calls `fix_generator_agent(state)` directly (not a graph run), injects human feedback as `critic_feedback`, stays on approval screen with updated patch

---

## All 8 Agents — How Each Works

### 1. Correlation Agent (`agents/correlation_agent.py`)

- **Reads:** `raw_complaints`, `raw_logs`
- **Writes:** `correlated_error`, `affected_customers`
- **Prompt strategy:** Strict JSON output — `{"correlated_error": "...", "affected_customers": ["Full Name 1", ...]}`
- **Safety:** Strips markdown code fences before JSON parse; falls back to `re.search(r'\{.*\}', text, re.DOTALL)` if parse fails
- **Key rule:** Extract customer names from complaints only — never from user IDs in logs (user_alice_001 → "Alice Johnson")

### 2. Severity Agent (`agents/severity_agent.py`)

- **Reads:** `correlated_error`, `affected_customers`, `raw_logs` (first 800 chars)
- **Writes:** `severity`, `severity_reason`
- **Classification rules:**
  - P0: payment/billing, data loss, complete outage, 5+ customers, keywords "charged"/"lost data"/"all users down"
  - P1: core feature broken, 3–4 customers, keywords "urgent"/"deadline"/"broken"
  - P2: non-critical degradation, 1–2 customers, workaround likely exists
- **Fallback:** If JSON parse fails, derives severity from customer count alone

### 3. Root Cause Agent (`agents/root_cause_agent.py`)

- **Reads:** `correlated_error`, `raw_logs`
- **Writes:** `root_cause`, `relevant_files`
- **Key feature — RAG enrichment:** Calls `retrieve_context(correlated_error, top_k=3)` from ChromaDB, injects top-3 most similar past incidents as numbered context sections into the prompt
- **Output:** JSON `{"root_cause": "...", "relevant_files": ["file.py"]}`

### 4. Fix Generator Agent (`agents/fix_generator_agent.py`)

- **Reads:** `root_cause`, `relevant_files`, `raw_logs`, `critic_feedback`
- **Writes:** `code_patch`, `patch_explanation`
- **Output format — delimited (not JSON):** Avoids multiline JSON escaping issues
  ```
  ===FILE===
  data_processing.py
  ===ORIGINAL===
  result = items[index]
  ===FIXED===
  result = items[index] if index < len(items) else None
  ===EXPLANATION===
  Added bounds check before indexing to handle empty batch input.
  ```
- **When critic_feedback is set:** Prepends it to the prompt + adds "Do NOT repeat the previous approach"

### 5. Execution Agent (`agents/execution_agent.py`)

- **Reads:** `code_patch`, `retry_count`
- **Writes:** `test_results`, `tests_passed`, `retry_count` (+1)
- **What it does:**
  1. `parse_code_patch(patch_str)` — parses the delimited format into `{file, original, fixed, explanation}`
  2. `write_test_harness(patch)` — generates a synthetic `fixed_code.py` + `test_fix.py` in a `tempfile.mkdtemp()` directory. Tests cover: empty input, normal operation, boundary conditions, missing keys
  3. Runs pytest via `sys.executable -m pytest test_fix.py -v --tb=short` in subprocess
  4. Cleans up temp dir in `try/finally`
- **Docker mode:** If `SANDBOX_MODE=docker`, uses `docker.from_env()` with `network_mode="none"`, falls back to subprocess on any exception
- **Critical:** Increments `retry_count` here (not in the router) — otherwise the loop never terminates

### 6. Critic Agent (`agents/critic_agent.py`)

- **Reads:** `root_cause`, `code_patch`, `test_results`, `retry_count`, `critic_feedback`
- **Writes:** `critic_feedback`
- **Output format:**
  ```
  WHAT FAILED: (one sentence)
  WHY IT FAILED: (one or two sentences)
  NEXT ATTEMPT MUST:
  - (specific instruction 1)
  - (specific instruction 2)
  - (specific instruction 3)
  ```
- **On retry 2+:** Passes previous `critic_feedback` in prompt so it avoids repeating advice

### 7. Customer Response Agent (`agents/customer_response_agent.py`)

- **Reads:** `affected_customers`, `root_cause`, `tests_passed`, `escalate_to_human`
- **Writes:** `customer_replies`
- **Key optimization:** Batches all customers into a **single LLM call** using `---NEXT---` delimiter — avoids N separate API calls and N separate rate limit windows
- **Rules in prompt:** Use first name only, no technical details (no stack traces/file names), plain English, under 80 words, warm and professional
- **Output:** `["To: Alice Johnson\n\nHi Alice, ...", "To: Bob Martinez\n\nHi Bob, ..."]`

### 8. Incident Report Agent (`agents/incident_report_agent.py`)

- **Reads:** all state fields
- **Writes:** `postmortem_report`, `status`
- **Design:** Template-based for all factual sections (no hallucination risk). Only **one LLM call** for the "Prevention Recommendations" section (3–4 specific bullets)
- **Sets status = "complete"** (or "escalated" via the escalation node)

---

## The Retry / Escalation Router

Defined in `graph/workflow.py`:

```python
def route_after_execution(state: IncidentState) -> str:
    if state["tests_passed"]:
        return "customer_response"
    max_retries = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
    if state["retry_count"] >= max_retries:
        return "escalate"
    return "critic"
```

The **escalation node** generates a structured escalation report and sets `escalate_to_human=True` and `status="escalated"`. Slack sends to `SLACK_ESCALATION_CHANNEL`. GitHub PR is skipped. Customer replies are not drafted.

---

## LLM Client — Lazy Singleton with Exponential Backoff (`agents/__init__.py`)

```python
# One shared ChatGroq instance across all agents
llm = _LazyLLM()  # defers construction until first use

def _invoke_with_retry(*args, **kwargs):
    for attempt in range(4):  # up to 4 attempts
        try:
            return _get_llm().invoke(*args, **kwargs)
        except Exception as e:
            if "tokens per day" in str(e).lower():
                raise RuntimeError("Daily quota exhausted...")  # no retry
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s
                time.sleep(wait)
                continue
            raise
```

---

## RAG Layer (`rag/`)

**How it works:**

1. `python -m rag.ingestion` — reads all `.md` files from `rag/past_incidents/`, generates embeddings with `all-MiniLM-L6-v2`, upserts into ChromaDB (idempotent — uses filename as document ID)
2. At runtime, Root Cause Agent calls `retrieve_context(query, top_k=3)` — encodes the query, runs cosine similarity search, returns top-3 past incident texts
3. These are injected as numbered context sections into the root cause prompt

**ChromaDB setup details:**
- `chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)` — NOT deprecated `Client()`
- `get_or_create_collection(...)` — NOT `create_collection()` (raises on re-run)
- All singletons (`_client`, `_collection`, `_embedding_model`) are module-level globals, lazy-initialized

**4 knowledge-base documents:**
- `indexerror_incident.md` — IndexError bounds check fix
- `keyerror_incident.md` — KeyError missing dict key fix
- `timeout_incident.md` — connection pool exhaustion fix
- `attributeerror_incident.md` — NoneType attribute access fix

---

## Streamlit Frontend — 5-Phase State Machine (`frontend/app.py`)

The app uses `st.session_state["hitl_phase"]` to track which phase is shown. Five possible values:

| Phase | What's shown |
|---|---|
| `"input"` | Two text areas (logs, complaints) + Load Sample Data + Run button |
| `"running_phase1"` | Live agent activity with streaming text as each agent completes |
| `"awaiting_approval"` | Patch + approve/reject UI with severity badge |
| `"running_phase2"` | Phase 2 agent activity |
| `"complete"` | Metrics row + 5 result tabs + Slack/PR status |

**Key implementation details:**

- **Streaming output:** `st.empty()` placeholder → inside the LangGraph stream loop, when `root_cause` or `patch_explanation` are ready, calls `st.write_stream(_char_stream(text))` which yields one character at a time with `time.sleep(0.006)`
- **Greyed-out agents:** Agents that never ran (critic, escalate) show `st.caption("⬜ {label} — not triggered")` instead of being skipped silently
- **Severity badge:** `st.error()` for P0, `st.warning()` for P1, `st.info()` for P2
- **Session state keys:** `hitl_phase`, `hitl_state` (full state dict), `hitl_agent_log` (node → elapsed seconds), `hitl_run_start`, `last_result`, `run_time`, `slack_notified`, `github_pr_url`
- **`reset_run()`:** Clears all session state keys to return to the input form

**Result tabs:**
1. **Root Cause** — root cause text, relevant files, correlated error, customer names
2. **Fix Applied** — full code patch in code block, explanation
3. **Test Results** — pytest stdout/stderr, escalation warning if needed
4. **Customer Replies** — each reply in `st.info()` box with divider
5. **Postmortem** — full Markdown report + download button

---

## Slack Notifications (`notifications/slack.py`)

**Two auth options (configured via `.env`):**
- `SLACK_BOT_TOKEN=xoxb-...` → uses `slack_sdk.WebClient.chat_postMessage()`
- `SLACK_WEBHOOK_URL=https://hooks.slack.com/...` → uses `slack_sdk.webhook.WebhookClient`

**Message structure — Slack Block Kit with `attachments`:**

```python
attachment = {
    "color": "#e53935",   # P0=red, P1=orange, P2=yellow
    "blocks": [...],       # header, section with fields, divider, root cause, context footer
    "fallback": header_text,  # required to avoid SDK warnings
}
client.chat_postMessage(channel=channel, text=header_text, attachments=[attachment])
```

**Two message templates:**
- `_build_resolved_blocks()` — severity, error, files, customer count, root cause, run time, retry count
- `_build_escalated_blocks()` — severity, error, customers waiting, max retries exhausted message, last test failure snippet

**Important:** The bot must be invited to the channel with `/invite @bot-name` before it can post.

---

## GitHub PR Auto-Creation (`notifications/github_pr.py`)

**Only runs when:** `tests_passed=True` AND `GITHUB_TOKEN` AND `GITHUB_REPO` are set.

**Flow:**
1. Parse the code patch with `parse_code_patch(state["code_patch"])`
2. Create branch: `incident-fix/{severity}-{id}-{YYYYMMDD-HHMMSS}`
3. Fetch the actual file from the repo, apply `existing.replace(original.strip(), fixed.strip(), 1)` — real diff
4. Commit with message: `fix({file}): {short_error} (incident #{id})`
5. Open PR with rich Markdown body: severity badge, root cause, before/after code blocks, customer list, test validation summary

**Key design decision — mockable client:**

```python
def _get_github_client(token: str):
    from github import Auth, Github
    return Github(auth=Auth.Token(token))
```

This is a module-level function so tests can do `monkeypatch.setattr("notifications.github_pr._get_github_client", ...)`.

**Auth:** Use `Auth.Token(token)` — NOT the deprecated `Github(token)` constructor.

---

## SQLite Persistence (`db/history.py`)

One table: `incidents` with columns for all `IncidentState` fields. JSON arrays (`affected_customers`, `relevant_files`, `customer_replies`) are stored as JSON strings and decoded on read.

Key functions:
- `save_incident(state, run_time_seconds) -> int` — inserts and returns new row ID
- `list_incidents(limit=50) -> list[dict]` — summary rows, newest first (no postmortem/test_results to keep it fast)
- `get_incident(id) -> dict` — full record for the history detail view
- `get_analytics_data() -> list[dict]` — lightweight rows for all incidents (oldest first) for charts
- Schema migrations handled via `try/except ALTER TABLE ADD COLUMN`

---

## Analytics Dashboard (`frontend/pages/2_Analytics.py`)

Reads all incidents via `get_analytics_data()`. Shows:

1. **6 summary metrics** — total incidents, resolved, escalated, P0/P1/P2 counts, avg MTTR
2. **Severity distribution** — `px.pie` donut (hole=0.45) with P0=#e53935, P1=#fb8c00, P2=#fdd835
3. **Outcome distribution** — `px.pie` donut: Resolved vs Escalated
4. **Incidents over time** — `px.bar` stacked bar chart by severity per day
5. **MTTR by severity** — `px.bar` avg run time per severity level
6. **Retry distribution** — `px.bar` how many incidents needed 0/1/2/3 retries
7. **Incident matrix table** — all rows with severity/status/customers/run time

---

## Webhook API (`api/webhook.py`)

FastAPI app running on port 8000. Exposes:

- `GET /health` → `{"status": "ok"}`
- `POST /webhook/incident` → runs full pipeline synchronously via `app.invoke(state)` (the no-HITL graph), saves to SQLite, fires Slack + GitHub PR, returns `IncidentResult`

**Authentication:** Set `WEBHOOK_API_KEY` in `.env`. Pass it as `X-Api-Key` header. If empty, auth is disabled (dev mode).

**Request body:**
```json
{
  "logs": "ERROR ...\nTraceback...\nIndexError: list index out of range",
  "complaints": ["App crashes every time I upload a CSV!"],
  "source": "datadog"
}
```

---

## Docker Setup

**`Dockerfile`** (CPU-only torch to minimize image size):
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y gcc g++ curl
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

**`entrypoint.sh`:**
```bash
python -m rag.ingestion   # idempotent — safe to run every start
exec streamlit run frontend/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
```

**`docker-compose.yml`:** Two services — `app` (Streamlit on 8501) and `api` (FastAPI on 8000). Both share named volumes `chroma_data` and `app_data` for persistence across restarts.

---

## Environment Variables (`.env.example`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | From console.groq.com (free tier) |
| `LLM_MODEL` | No | `llama-3.3-70b-versatile` | Use `llama-3.1-8b-instant` for higher rate limits |
| `GROQ_TEMPERATURE` | No | `0.2` | LLM temperature 0–1 |
| `GROQ_MAX_TOKENS` | No | `4096` | Max tokens per call |
| `MAX_RETRY_ATTEMPTS` | No | `3` | Fix retries before escalation. Set to `1` to force escalation in demos |
| `SANDBOX_MODE` | No | `subprocess` | `subprocess` or `docker` |
| `INCIDENT_DB_PATH` | No | `./incidents.db` | SQLite path |
| `CHROMA_PERSIST_DIR` | No | `./rag/chroma_db` | ChromaDB path |
| `SLACK_BOT_TOKEN` | No | — | `xoxb-...` — needs `chat:write` scope |
| `SLACK_WEBHOOK_URL` | No | — | Alternative to bot token |
| `SLACK_INCIDENT_CHANNEL` | No | `#incidents` | Resolved incident channel |
| `SLACK_ESCALATION_CHANNEL` | No | Same as above | Escalation alerts channel |
| `GITHUB_TOKEN` | No | — | PAT with `repo` scope |
| `GITHUB_REPO` | No | — | `owner/repository-name` |
| `GITHUB_BASE_BRANCH` | No | `main` | PR target branch |
| `WEBHOOK_API_KEY` | No | — | API key for webhook endpoint |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Set GROQ_API_KEY at minimum

# 3. Ingest past incidents into ChromaDB (run once)
python -m rag.ingestion

# 4. Run the dashboard
streamlit run frontend/app.py

# 5. (Optional) Run webhook API
uvicorn api.webhook:app --port 8000 --reload

# Run tests (no API key needed, ~8 seconds)
pytest tests/ -m "not integration" -v

# Docker
docker compose up --build
```

---

## The 7 Test Scenarios (`test_cases.txt`)

Each maps to a real buggy file in `app/` so GitHub PRs show clean, mergeable diffs:

| # | Scenario | Expected Severity | Bug location |
|---|---|---|---|
| 1 | IndexError — file upload crash | P1 | `data_processing.py:42` |
| 2 | KeyError — payment failure | P0 | `payment_service.py:87` |
| 3 | DB timeout — connection pool | P1 | `database_service.py:134` |
| 4 | AttributeError — welcome email | P2 | `notification_service.py:78` |
| 5 | Mass outage — service down | P0 | `api_gateway.py:23` |
| 6 | ZeroDivisionError — analytics | P2 | `analytics_service.py:91` |
| 7 | Reject → regenerate HITL flow | P2 | `order_service.py:55` |

**Tips:**
- Set `MAX_RETRY_ATTEMPTS=1` to force escalation quickly
- Use `LLM_MODEL=llama-3.1-8b-instant` if you hit daily token limits
- Test case 7 specifically tests the human rejection → patch regeneration cycle

---

## Key Design Decisions and Gotchas

| Issue | Solution |
|---|---|
| HITL without LangGraph checkpointers | Split into two compiled graphs; save state in `st.session_state` between phases |
| LLM JSON with markdown code fences | Strip ` ```json ``` ` wrappers; fallback `re.search(r'\{.*\}', text, re.DOTALL)` |
| Multiline code in LLM output | Delimited format (`===FILE=== ===ORIGINAL=== ===FIXED===`) instead of JSON |
| Infinite retry loop | `retry_count` incremented in execution agent (not router); router checks it |
| ChromaDB re-run failure | `get_or_create_collection()` + `PersistentClient`; filename as doc ID for idempotency |
| LangGraph node return | Return only changed fields as `dict` — never the full state |
| `python` vs `sys.executable` | Always `sys.executable` in subprocess calls (picks up the right venv) |
| Streamlit tab re-runs | Cache full state in `st.session_state` so switching tabs doesn't re-run pipeline |
| PyGithub deprecated constructor | `Github(auth=Auth.Token(token))` — not `Github(token)` |
| GitHub client not mockable | `_get_github_client(token)` at module level — tests monkeypatch this function |
| Slack bot not in channel | Bot must be `/invite`d before it can post |
| Slack SDK warnings | Pass `text=header_text` to `chat_postMessage()` + `fallback=header_text` in attachment |
| Docker torch image size | Install CPU-only torch first via `--index-url https://download.pytorch.org/whl/cpu` |
| Streamlit torch watcher warning | `.streamlit/config.toml` with `fileWatcherType = "poll"` |
| Groq rate limits (6k tokens/min free) | Hard token budgets; batch all customers in one LLM call; exponential backoff 2s→4s→8s→16s |
| Daily Groq quota exhausted | Detected from error string — raises `RuntimeError` immediately (no retry); shown as `st.error()` in UI |

---

*This context document was generated from the actual source code. All code snippets, file paths, and design notes reflect the real implementation.*
