# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize RAG knowledge base (required before first run)
python -m rag.ingestion

# Run Streamlit dashboard
streamlit run frontend/app.py          # http://localhost:8501

# Run webhook API (separate terminal)
uvicorn api.webhook:app --port 8000 --reload

# Docker (both services + persistent volumes)
docker compose up --build

# Tests
pytest tests/ -m "not integration" -v  # Unit tests (no API key needed)
pytest tests/ -m integration -v        # Full pipeline (requires GROQ_API_KEY)
pytest tests/test_agents.py -v         # Single test file

# Benchmark (7 end-to-end scenarios against ground truth)
python -m tests.benchmark.run_benchmark
python -m tests.benchmark.run_benchmark --max 3  # Faster subset

# Export benchmark results as Markdown
python scripts/export_benchmark_report.py
python scripts/export_benchmark_report.py --output docs/benchmark-results.generated.md
```

## Architecture

This is a two-phase, human-in-the-loop incident response pipeline. All agents share a single `IncidentState` TypedDict defined in [agents/state.py](agents/state.py). Agents return only the fields they update; LangGraph merges them automatically.

### Two-Phase LangGraph Split

The pipeline is split into two compiled graphs to support human approval without a persistent checkpointer:

- **`phase1_app`** — Diagnosis: `correlation → severity → root_cause → fix_generator → END`
- **`phase2_app`** — Execution: `execution → [critic ↔ fix_generator retry loop] → customer_response → incident_report → END`
- **`app`** — Full pipeline without HITL gate (used by tests and webhook API)

All three are compiled in [graph/workflow.py](graph/workflow.py).

### The 8 Agents

| Agent | File | Key Output Fields |
|---|---|---|
| Correlation | [agents/correlation_agent.py](agents/correlation_agent.py) | `correlated_error`, `affected_customers` |
| Severity | [agents/severity_agent.py](agents/severity_agent.py) | `severity` (P0/P1/P2), `severity_reason` |
| Root Cause | [agents/root_cause_agent.py](agents/root_cause_agent.py) | `root_cause`, `relevant_files`, `rag_similarity_score` |
| Fix Generator | [agents/fix_generator_agent.py](agents/fix_generator_agent.py) | `code_patch`, `patch_explanation` |
| Execution | [agents/execution_agent.py](agents/execution_agent.py) | `test_results`, `tests_passed`, `retry_count` |
| Critic | [agents/critic_agent.py](agents/critic_agent.py) | `critic_feedback` |
| Customer Response | [agents/customer_response_agent.py](agents/customer_response_agent.py) | `customer_replies` |
| Incident Report | [agents/incident_report_agent.py](agents/incident_report_agent.py) | `postmortem_report`, `status` |

### Self-Healing Retry Loop

Execution Agent increments `retry_count` on failure. `route_after_execution()` in [graph/workflow.py](graph/workflow.py) routes:
- `tests_passed=True` → customer_response
- `retry_count >= MAX_RETRY_ATTEMPTS` → escalate
- else → critic (which feeds structured feedback back to fix_generator)

### HITL Gate (Streamlit)

The Streamlit frontend in [frontend/app.py](frontend/app.py) implements a 5-phase state machine:
1. Runs `phase1_app.stream()`, caches result in `st.session_state["hitl_state"]`
2. Displays patch diff + confidence score, waits for user approval
3. **Approve** → passes saved state into `phase2_app.stream()`
4. **Reject** → calls `fix_generator_agent(state)` directly with human feedback as `critic_feedback`, re-renders approval screen

### RAG Knowledge Base

Root Cause Agent queries ChromaDB (via [rag/vectorstore.py](rag/vectorstore.py)) using `correlated_error` as the query. Retrieves top-3 similar past incidents from [rag/past_incidents/](rag/past_incidents/). The top-1 cosine distance is stored as `rag_similarity_score` and used in the confidence score calculation.

After a resolved incident is saved to SQLite, it is automatically re-ingested into ChromaDB so the system learns from history.

### Confidence Score

Computed at the HITL gate from three signals (0.0–1.0 total):
- RAG similarity: `max(0, 1 − cosine_distance) × 0.4`
- First-attempt quality: retry 0 → 0.40, retry 1 → 0.20, retry ≥2 → 0.00
- Patch scope: patch < 20 lines → 0.20, else 0.00

### LLM Client

The shared LLM singleton with exponential backoff and fallback provider switching lives in [agents/__init__.py](agents/__init__.py). Primary: Groq `llama-3.3-70b-versatile`. Fallback: Gemini/OpenAI/Anthropic (lazy import, auto-activates on quota exhaustion via `FALLBACK_LLM_PROVIDER` env var).

### Patch Format

Fix Generator uses a delimited format (not JSON) to avoid escaping issues:
```
===FILE: path/to/file.py===
<full file content>
===END===
```
Parsed by regex in the execution agent.

### Execution Sandbox

Execution Agent discovers real test files using glob patterns (`tests/test_<module>.py`, `test_<module>.py`, `**/test*<stem>*`). Falls back to a synthetic harness if none found. Runs via subprocess by default; set `SANDBOX_MODE=docker` for container isolation.

## Troubleshooting

**`KeyError: '_type'` from ChromaDB during tests or startup**

The on-disk ChromaDB database (`rag/chroma_db/`) was created with an older ChromaDB version (≤ 0.5.x) that didn't store a `_type` field in the collection config. ChromaDB 0.6+ expects it. Fix by deleting and rebuilding — the markdown files in `rag/past_incidents/` are the source of truth, so nothing is lost:

```bash
rm -rf rag/chroma_db
python -m rag.ingestion
```

---

## Key Environment Variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | From console.groq.com |
| `LLM_MODEL` | No | `llama-3.3-70b-versatile` | Use `llama-3.1-8b-instant` for higher rate limits |
| `MAX_RETRY_ATTEMPTS` | No | `3` | Set to `1` for quick escalation demos |
| `SANDBOX_MODE` | No | `subprocess` | `subprocess` or `docker` |
| `SLACK_BOT_TOKEN` / `SLACK_WEBHOOK_URL` | No | — | Either triggers Slack notifications |
| `GITHUB_TOKEN` + `GITHUB_REPO` | No | — | Required for GitHub PR creation |
| `FALLBACK_LLM_PROVIDER` | No | — | `gemini`, `openai`, or `anthropic` |

See [.env.example](.env.example) for the full list.

## Test Fixtures

[tests/conftest.py](tests/conftest.py) provides pytest fixtures for pre-built `IncidentState` objects at various pipeline stages (`sample_state`, `state_after_correlation`, etc.) — use these when adding new tests rather than building state from scratch.

## Sample Test Scenarios

[test_cases.txt](test_cases.txt) contains 7 ready-to-paste log + complaint pairs for manual dashboard testing, covering IndexError, KeyError, TimeoutError, AttributeError, and ZeroDivisionError cases.
