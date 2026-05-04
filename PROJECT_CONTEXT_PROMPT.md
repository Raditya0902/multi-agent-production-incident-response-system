# PROJECT CONTEXT — Multi-Agent Production Incident Response System

> **How to use this file:** Paste the entire contents into a new Claude conversation.
> Claude will then have complete context about this project and can help you with
> anything — debugging, feature additions, explaining code, architecture questions, etc.

---

## What This Project Is

A fully autonomous AI pipeline that handles production software incidents end-to-end. When something breaks in production, you paste the error logs and customer complaints into a Streamlit dashboard and click **Run**. Within ~90 seconds, the system has diagnosed the root cause, written a code fix, tested it in a sandbox, drafted personalized replies to every affected customer, sent a Slack notification, and opened a GitHub PR — all with a human approval gate before any code is touched.

**GitHub repo:** `https://github.com/Raditya0902/multi-agent-production-incident-response-system`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (`StateGraph`) |
| Primary LLM | Groq API — `llama-3.3-70b-versatile` (default) |
| Fallback LLM | Gemini / OpenAI / Anthropic (auto-activates on Groq quota exhaustion) |
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
  __init__.py              # Lazy LLM singleton, exponential backoff, fallback LLM switcher
  state.py                 # IncidentState TypedDict + create_initial_state()
  correlation_agent.py     # Links errors to customer names from logs/complaints
  severity_agent.py        # Classifies P0 / P1 / P2 with reasoning
  root_cause_agent.py      # RAG-augmented root cause diagnosis; records rag_similarity_score
  fix_generator_agent.py   # Generates code patches in delimited format
  execution_agent.py       # Real test discovery + subprocess/Docker sandbox runner
  critic_agent.py          # Analyzes test failures, guides next fix attempt
  customer_response_agent.py   # Drafts personalized replies (all in one LLM call)
  incident_report_agent.py     # Generates Markdown postmortem

graph/
  workflow.py              # Three compiled LangGraph graphs: phase1_app, phase2_app, app

rag/
  vectorstore.py           # ChromaDB wrapper — retrieve_context(), retrieve_context_with_scores(), add_documents()
  ingestion.py             # Ingest past_incidents/*.md (+ real/ subdir) into ChromaDB — run once before starting
  past_incidents/          # Markdown knowledge-base files (IndexError, KeyError, Timeout, AttributeError)
    real/                  # Optional: real postmortems (fetched by rag/scripts/fetch_real_postmortems.py)
  chroma_db/               # Persisted vector index (auto-created)
  scripts/
    fetch_real_postmortems.py  # Fetch real postmortems from danluu/post-mortems repo

app/                       # Buggy sample source files (one per test scenario)
  data_processing.py       # IndexError at line 42
  payment_service.py       # KeyError at line 87
  api_gateway.py           # KeyError at line 23
  notification_service.py  # AttributeError at line 78
  order_service.py         # IndexError at line 55
  analytics_service.py     # ZeroDivisionError at line 91
  database_service.py      # TimeoutError at line 134

db/
  history.py               # SQLite CRUD — save_incident(), list_incidents(), get_analytics_data(), export_as_postmortem_doc()

notifications/
  slack.py                 # Block Kit messages via bot token or webhook URL
  github_pr.py             # Branch, commit, and PR creation via PyGithub

api/
  webhook.py               # FastAPI webhook — POST /webhook/incident[?dry_run=true]

frontend/
  app.py                   # Main Streamlit app (5-phase HITL state machine)
  pages/
    1_History.py           # Incident history with severity filter + postmortem download
    2_Analytics.py         # Plotly charts: severity, MTTR, retries, outcome matrix + Benchmark tab

tests/
  conftest.py
  test_agents.py           # Patch parser, router logic, RAG, execution sandbox
  test_history.py          # SQLite CRUD with temp DB isolation
  test_slack.py            # Block builders and transport layer
  test_github_pr.py        # Branch naming, patch application, PR body
  benchmark/
    ground_truth.py        # Expected fix patterns per source file
    run_benchmark.py       # End-to-end evaluation runner; saves results/latest.json

sandbox/
  Dockerfile               # Isolated container for code execution (optional)

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
    raw_complaints: List[str]       # one complaint message per list item
    raw_logs: str                   # raw error logs / stack trace

    # Correlation Agent output
    correlated_error: str           # 1-2 sentence error summary
    affected_customers: List[str]   # ["Alice Johnson", "Bob Martinez"]

    # Severity Agent output
    severity: str                   # "P0" | "P1" | "P2"
    severity_reason: str            # one-sentence justification

    # Root Cause Agent output
    root_cause: str                 # detailed diagnosis
    relevant_files: List[str]       # ["data_processing.py", ...]
    rag_similarity_score: float     # top-1 ChromaDB cosine distance (0=identical, 2=opposite)

    # Fix Generator output
    code_patch: str                 # full delimited patch text
    patch_explanation: str          # extracted one-line explanation

    # Execution Agent output
    test_results: str               # full pytest stdout+stderr
    tests_passed: bool
    used_real_tests: bool           # True when validated against real repo test suite

    # Critic Agent / retry loop
    retry_count: int                # incremented by execution_agent each attempt
    critic_feedback: str            # structured WHAT FAILED / WHY / NEXT ATTEMPT MUST

    # Downstream outputs
    customer_replies: List[str]     # ["To: Alice\n\n...", "To: Bob\n\n..."]
    postmortem_report: str          # full Markdown postmortem

    # Control flags
    escalate_to_human: bool         # True when max retries exhausted
    status: str                     # "started" | "correlation_complete" | ... | "complete" | "escalated"
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
2. UI switches to "awaiting_approval" — shows the patch diff + confidence score + Approve / Reject buttons
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
- **Writes:** `root_cause`, `relevant_files`, `rag_similarity_score`
- **Key feature — RAG enrichment:** Calls `retrieve_context_with_scores(correlated_error, top_k=3)` from ChromaDB, injects top-3 most similar past incidents as numbered context sections into the prompt. Records the top-1 cosine distance as `rag_similarity_score` (used downstream for confidence scoring).
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
- **Explicit guard-pattern rules in prompt:** bounds checks (`if index < len(collection)`), `.get()` for missing keys, `if x is None:` guards, `if denominator == 0:` for zero-division
- **When critic_feedback is set:** Prepends it to the prompt + adds "Do NOT repeat the previous approach"

### 5. Execution Agent (`agents/execution_agent.py`)

- **Reads:** `code_patch`, `retry_count`
- **Writes:** `test_results`, `tests_passed`, `used_real_tests`, `retry_count` (+1)
- **Real test discovery (new):**
  1. `find_real_test_file(module_filename)` — searches `tests/test_<module>.py`, then project root, then `**/*test*<stem>*`
  2. `find_source_file(module_filename)` — searches `app/<file>`, project root, then recursive glob
  3. If found: copies patched source + real test file into `tempfile.mkdtemp()`, runs real pytest, sets `used_real_tests=True`
  4. If not found: generates synthetic harness via `write_test_harness(patch)`, sets `used_real_tests=False` + appends warning to test output
- **Synthetic harness:** `_build_fixed_module()` wraps the LLM's fixed snippet in a testable function for IndexError/KeyError cases. For other error types it uses a hardcoded trivial harness (context variables like `pool`, `session` aren't available in a generic wrapper).
- **Runs pytest via:** `[sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]` in subprocess
- **Docker mode:** If `SANDBOX_MODE=docker`, uses `docker.from_env()`, falls back to subprocess on any exception
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
- **Key optimization:** Batches all customers into a **single LLM call** using `---NEXT---` delimiter — avoids N separate API calls
- **Rules in prompt:** Use first name only, no technical details (no stack traces/file names), plain English, under 80 words, warm and professional

### 8. Incident Report Agent (`agents/incident_report_agent.py`)

- **Reads:** all state fields
- **Writes:** `postmortem_report`, `status`
- **Design:** Template-based for all factual sections (no hallucination risk). Only **one LLM call** for "Prevention Recommendations" (3–4 specific bullets).
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

The **escalation node** generates a structured escalation report, sets `escalate_to_human=True` and `status="escalated"`. Slack sends to `SLACK_ESCALATION_CHANNEL`. GitHub PR is skipped. Customer replies are not drafted.

---

## LLM Client — Lazy Singleton with Fallback (`agents/__init__.py`)

```python
# One shared ChatGroq instance across all agents
llm = _LazyLLM()  # defers construction until first use

def _invoke_with_retry(*args, **kwargs):
    global _using_fallback

    # If already switched to fallback, use it
    if _using_fallback:
        return _invoke_fallback_with_retry(*args, **kwargs)

    for attempt in range(4):  # up to 4 attempts: waits 2s, 4s, 8s, 16s
        try:
            return _get_llm().invoke(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()

            if "tokens per day" in err_str or "tpd" in err_str:
                # Daily quota exhausted — try fallback, or raise
                fallback = _get_fallback_llm()
                if fallback:
                    _using_fallback = True
                    return _invoke_fallback_with_retry(*args, **kwargs)
                raise RuntimeError("Groq daily token limit reached...")

            if "rate_limit" in err_str or "429" in err_str:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue
            raise
```

**Fallback LLM** (`_get_fallback_llm()`):
- Reads `FALLBACK_LLM_PROVIDER` env var — supports `"gemini"`, `"openai"`, `"anthropic"`
- Lazily imports the matching `langchain-*` package (must be installed separately)
- `is_using_fallback()` is exported — `frontend/app.py` checks it to show a sidebar warning

---

## Confidence Score (`frontend/app.py` — `calculate_confidence()`)

Shown at the HITL approval gate. Three signals summed to a 0.0–1.0 score:

```python
def calculate_confidence(state: dict) -> tuple[float, dict]:
    # Signal 1: RAG similarity (0–0.4 weight)
    rag_distance = state.get("rag_similarity_score", 1.0)
    rag_sim = max(0.0, 1.0 - rag_distance)     # cosine distance → similarity
    signals["rag_similarity"] = rag_sim * 0.4

    # Signal 2: First attempt vs retry (0–0.4 weight)
    retry_count = state.get("retry_count", 0)
    signals["attempt_quality"] = max(0.0, 0.4 - retry_count * 0.2)
    # retry 0 → 0.40, retry 1 → 0.20, retry ≥2 → 0.00

    # Signal 3: Patch scope (0–0.2 weight)
    patch_lines = state.get("code_patch", "").count("\n")
    signals["patch_scope"] = 0.2 if patch_lines < 20 else 0.0

    total = round(sum(signals.values()), 2)
    return total, signals
```

- **≥ 0.8** → green "High confidence" badge
- **0.5 – 0.8** → yellow "Medium confidence — review carefully"
- **< 0.5** → red "Low confidence — manual review strongly recommended"

---

## Diff View at Approval Gate (`frontend/app.py` — `_render_patch_diff()`)

Instead of showing the raw patch text, the HITL gate renders a **unified diff** (`difflib.unified_diff`) of the original vs fixed code, enriched with 5 lines of surrounding context read from the real source file in `app/`. Falls back to raw text if the source file can't be found.

---

## RAG Auto-Feedback Loop (`frontend/app.py`)

After a successful Phase 2 run (tests passed, no escalation):

```python
doc_text = export_as_postmortem_doc(incident_id)
add_documents([{
    "id": f"incident_{incident_id}",
    "content": doc_text,
    "metadata": {"source": "auto_feedback", "incident_id": str(incident_id)},
}])
```

`export_as_postmortem_doc()` in `db/history.py` formats the SQLite incident as a Markdown postmortem document suitable for RAG retrieval. A toast notification ("📚 Incident added to RAG knowledge base") confirms it happened. This means the system learns from every resolved incident automatically.

---

## RAG Layer (`rag/`)

**How it works:**

1. `python -m rag.ingestion` — reads all `.md` files from `rag/past_incidents/` (and `real/` subdir if present), generates embeddings with `all-MiniLM-L6-v2`, upserts into ChromaDB (idempotent — uses filename as document ID)
2. At runtime, Root Cause Agent calls `retrieve_context_with_scores(query, top_k=3)` — encodes the query, runs cosine similarity search, returns `[(doc_text, distance), ...]` tuples
3. The top-3 texts are injected as numbered context sections into the root cause prompt; the top-1 distance is stored as `rag_similarity_score`

**Two vectorstore functions:**
- `retrieve_context(query, top_k)` — returns `List[str]` (legacy, still used in some tests)
- `retrieve_context_with_scores(query, top_k)` — returns `List[tuple[str, float]]` (used by root_cause_agent)

**ChromaDB setup details:**
- `chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)` — NOT deprecated `Client()`
- `get_or_create_collection(...)` — NOT `create_collection()` (raises on re-run)
- All singletons (`_client`, `_collection`, `_embedding_model`) are module-level globals, lazy-initialized

**Ingestion sources:**
- `rag/past_incidents/*.md` — synthetic scenario documents (4 built-in)
- `rag/past_incidents/real/*.md` — real postmortems (fetched via `rag/scripts/fetch_real_postmortems.py`)
- Auto-ingested resolved incidents (via RAG feedback loop above)

---

## Streamlit Frontend — 5-Phase State Machine (`frontend/app.py`)

The app uses `st.session_state["hitl_phase"]` to track which phase is shown. Five possible values:

| Phase | What's shown |
|---|---|
| `"input"` | Two text areas (logs, complaints) + Load Sample Data + Run button |
| `"running_phase1"` | Live agent activity with streaming text as each agent completes |
| `"awaiting_approval"` | Confidence score + unified diff + Approve / Reject UI |
| `"running_phase2"` | Phase 2 agent activity |
| `"complete"` | Metrics row + 5 result tabs + Slack/PR status |

**Key implementation details:**

- **Streaming output:** `st.empty()` placeholder → inside the LangGraph stream loop, when `root_cause` or `patch_explanation` are ready, calls `st.write_stream(_char_stream(text))` which yields one character at a time with `time.sleep(0.006)`
- **Greyed-out agents:** Agents that never ran (critic, escalate) show `st.caption("⬜ {label} — not triggered")` instead of being skipped silently
- **Fallback warning:** `is_using_fallback()` checked on every phase render — shows `st.sidebar.warning()` if Groq quota was exceeded
- **Severity badge:** `st.error()` for P0, `st.warning()` for P1, `st.info()` for P2
- **`used_real_tests` banner:** `st.success("Validated against real repo test suite")` or `st.warning("Synthetic tests used")`
- **Session state keys:** `hitl_phase`, `hitl_state`, `hitl_agent_log`, `hitl_run_start`, `last_result`, `run_time`, `slack_notified`, `github_pr_url`, `incident_id`
- **`reset_run()`:** Clears all session state keys to return to the input form

**Result tabs:**
1. **Root Cause** — root cause text, relevant files, correlated error, customer names
2. **Fix Applied** — unified diff view, explanation
3. **Test Results** — pytest stdout/stderr, `used_real_tests` banner, escalation warning if needed
4. **Customer Replies** — each reply in `st.info()` box with divider
5. **Postmortem** — full Markdown report + download button

---

## Benchmark Suite (`tests/benchmark/`)

```bash
python -m tests.benchmark.run_benchmark              # run all 7 cases, print table
python -m tests.benchmark.run_benchmark --save-history  # also append to history.jsonl
python -m tests.benchmark.run_benchmark --max 3      # run only first 3
```

**`ground_truth.py`** — maps each `target_file` to the expected `correct_fix_pattern` (string or list of strings). The runner checks whether the LLM's patch contains the ground-truth pattern.

**`run_benchmark.py`** — runs each of the 7 test cases end-to-end via `pipeline_app.invoke(state)`, records `tests_passed`, `patch_correct`, `false_positive`, `retry_count`, `elapsed`. Computes aggregate metrics and saves to `tests/benchmark/results/latest.json`.

**Metrics:**

| Metric | Description |
|---|---|
| `patch_correctness_pct` | % where patch contains the correct fix pattern |
| `first_attempt_success_rate` | % where tests passed on retry_count ≤ 1 |
| `retry_success_rate` | % of failed attempt-1 cases that succeeded by attempt 3 |
| `false_positive_rate` | % where tests passed but patch didn't contain correct pattern |
| `avg_run_time_seconds` | Average wall-clock time per scenario |
| `escalation_rate` | % escalated (max retries hit) |

The **Analytics page** also exposes a "Run Benchmark" button that calls `python -m tests.benchmark.run_benchmark --save-history` as a subprocess and displays results in a dataframe.

---

## Slack Notifications (`notifications/slack.py`)

**Two auth options:**
- `SLACK_BOT_TOKEN=xoxb-...` → `slack_sdk.WebClient.chat_postMessage()`
- `SLACK_WEBHOOK_URL=https://hooks.slack.com/...` → `slack_sdk.webhook.WebhookClient`

**Message structure — Slack Block Kit with `attachments`:**
```python
attachment = {
    "color": "#e53935",   # P0=red, P1=orange, P2=yellow
    "blocks": [...],
    "fallback": header_text,  # required to avoid SDK warnings
}
client.chat_postMessage(channel=channel, text=header_text, attachments=[attachment])
```

---

## GitHub PR Auto-Creation (`notifications/github_pr.py`)

**Only runs when:** `tests_passed=True` AND `GITHUB_TOKEN` AND `GITHUB_REPO` are set.

**Flow:**
1. Parse the code patch with `parse_code_patch(state["code_patch"])`
2. Create branch: `incident-fix/{severity}-{id}-{YYYYMMDD-HHMMSS}`
3. Fetch the actual file from the repo, apply `existing.replace(original.strip(), fixed.strip(), 1)` — real diff
4. Commit with message: `fix({file}): {short_error} (incident #{id})`
5. Open PR with rich Markdown body: severity badge, root cause, before/after code blocks, customer list, test validation summary

---

## SQLite Persistence (`db/history.py`)

One table: `incidents` with columns for all `IncidentState` fields. JSON arrays (`affected_customers`, `relevant_files`, `customer_replies`) stored as JSON strings and decoded on read.

Key functions:
- `save_incident(state, run_time_seconds) -> int` — inserts and returns new row ID
- `list_incidents(limit=50) -> list[dict]` — summary rows, newest first
- `get_incident(id) -> dict` — full record for the history detail view
- `get_analytics_data() -> list[dict]` — lightweight rows for all incidents for charts
- `export_as_postmortem_doc(incident_id) -> str` — formats a resolved incident as a Markdown postmortem for RAG re-ingestion
- Schema migrations handled via `try/except ALTER TABLE ADD COLUMN`

---

## Webhook API (`api/webhook.py`)

FastAPI app on port 8000.

- `GET /health` → `{"status": "ok"}`
- `POST /webhook/incident` → runs full pipeline synchronously via `app.invoke(state)`, saves to SQLite, fires Slack + GitHub PR, returns `IncidentResult`
- `POST /webhook/incident?dry_run=true` → runs full pipeline but **skips all side effects** (no SQLite save, no Slack, no GitHub PR). Returns result with `"dry_run": true` and `"note": "Dry run — no side effects triggered"`. Useful for external monitoring tools evaluating severity without triggering notifications.

**Authentication:** Set `WEBHOOK_API_KEY` in `.env`. Pass as `X-Api-Key` header. Empty = no auth (dev mode).

---

## Docker Setup

**`docker-compose.yml`:** Two services — `app` (Streamlit on 8501) and `api` (FastAPI on 8000). Both share named volumes `chroma_data` and `app_data` for persistence across restarts.

**`entrypoint.sh`:**
```bash
python -m rag.ingestion   # idempotent — safe to run every start
exec streamlit run frontend/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
```

**CPU-only torch** in Dockerfile (`--index-url https://download.pytorch.org/whl/cpu`) to minimize image size.

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
| `FALLBACK_LLM_PROVIDER` | No | — | `"gemini"`, `"openai"`, or `"anthropic"` — auto-activates on Groq quota exhaustion |
| `GOOGLE_API_KEY` | No | — | Required when `FALLBACK_LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY` | No | — | Required when `FALLBACK_LLM_PROVIDER=openai` |
| `ANTHROPIC_API_KEY` | No | — | Required when `FALLBACK_LLM_PROVIDER=anthropic` |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
# For fallback LLM: pip install langchain-google-genai  (or langchain-openai / langchain-anthropic)

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

# Run benchmark (requires GROQ_API_KEY)
python -m tests.benchmark.run_benchmark

# Docker
docker compose up --build
```

---

## The 7 Test Scenarios (`test_cases.txt`)

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
| Groq daily quota exhausted | Detected from error string — auto-switches to fallback LLM if configured, else `RuntimeError` |
| Fallback LLM package not installed | Lazy import inside `_get_fallback_llm()` — warns and returns `None` gracefully |
| Synthetic test harness context mismatch | Context-dependent errors (Timeout, AttributeError) use a trivial fallback harness; correctness evaluated via patch pattern matching instead |

---

*This context document was generated from the actual source code. All code snippets, file paths, and design notes reflect the real implementation as of the latest commit.*
