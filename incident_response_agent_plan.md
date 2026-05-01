# Multi-Agent Production Incident Response System
## Complete Project Plan for Implementation

---

## 1. Project Overview

Build a **Multi-Agent Production Incident Response System** that simultaneously monitors:
- Incoming customer support complaints
- Application error logs / stack traces / failed builds

Multiple specialized AI agents collaborate to **correlate, diagnose, fix, validate, and communicate** — automatically — closing the loop between engineering and customer support during a production incident.

---

## 2. Problem Statement

When production breaks, two things happen simultaneously:
1. Engineers scramble through logs trying to find the root cause
2. Customers flood support channels with complaints

No existing tool connects both streams intelligently. This system does.

**Input:** Customer complaints + error logs/stack traces  
**Output:** Bug fixed + customers notified + postmortem report generated

---

## 3. System Architecture

### 3.1 High-Level Flow

```
[Customer Complaints]  +  [Error Logs / Stack Traces]
            |                        |
            └──────────┬─────────────┘
                       ↓
             [1. Correlation Agent]
               Links complaints to specific errors
                       ↓
             [2. Root Cause Agent]  ←── RAG (past incidents + docs)
               Diagnoses what broke and why
                       ↓
             [3. Fix Generator Agent]
               Writes code patch / suggests fix
                       ↓
             [4. Execution Agent]
               Runs tests in Docker sandbox
                       ↓
                 Tests Pass? ──No──→ [5. Critic Agent]
                       |                    |
                      Yes                   └──→ loops back to Fix Generator
                       ↓
             [6. Customer Response Agent]
               Drafts personalized replies to affected customers
                       ↓
             [7. Incident Report Agent]
               Auto-generates postmortem document
```

### 3.2 Agent Responsibilities

| Agent | Input | Output |
|---|---|---|
| Correlation Agent | Customer messages + error logs | Linked complaint-to-error mapping |
| Root Cause Agent | Correlated data + RAG context | Root cause hypothesis |
| Fix Generator Agent | Root cause + code context | Code patch |
| Execution Agent | Code patch | Test results (pass/fail) |
| Critic Agent | Failed test output | Revised fix instructions |
| Customer Response Agent | Root cause + affected users | Draft email/message replies |
| Incident Report Agent | Full incident data | Postmortem markdown report |

### 3.3 Self-Healing Loop

```
Fix Generator → Execution Agent → [FAIL] → Critic Agent → Fix Generator
                               → [PASS] → Customer Response + Report
```

Maximum retry limit: **3 iterations** (configurable). If unresolved after max retries, escalate to human.

---

## 4. Tech Stack

| Layer | Technology |
|---|---|
| Agent Orchestration | **LangGraph** (Python) |
| LLM | **Groq** (LLaMA 3.1 70B or Qwen 3) — free tier |
| RAG / Vector DB | **ChromaDB** (local) or Qdrant |
| Embeddings | `sentence-transformers` (all-MiniLM-L6-v2) |
| Code Execution | **Docker** sandbox (Python subprocess fallback) |
| Testing | **pytest** |
| Frontend | **Streamlit** dashboard |
| GitHub Integration | **PyGithub** (optional, for real repo PRs) |
| Environment | Python 3.11+, `.env` for API keys |

---

## 5. Project Structure

```
incident-response-agent/
│
├── agents/
│   ├── __init__.py
│   ├── correlation_agent.py       # Links complaints to errors
│   ├── root_cause_agent.py        # Diagnoses root cause using RAG
│   ├── fix_generator_agent.py     # Generates code patch
│   ├── execution_agent.py         # Runs code/tests in sandbox
│   ├── critic_agent.py            # Analyzes failed fix, suggests retry
│   ├── customer_response_agent.py # Drafts customer replies
│   └── incident_report_agent.py   # Generates postmortem report
│
├── graph/
│   ├── __init__.py
│   └── workflow.py                # LangGraph state machine definition
│
├── rag/
│   ├── __init__.py
│   ├── vectorstore.py             # ChromaDB setup and retrieval
│   ├── ingestion.py               # Ingest past incidents + docs
│   └── past_incidents/            # Sample past incident markdown files
│
├── sandbox/
│   ├── Dockerfile                 # Isolated code execution environment
│   └── runner.py                  # Executes code patches safely
│
├── data/
│   ├── sample_logs/               # Sample error logs for demo
│   │   ├── indexerror_log.txt
│   │   ├── keyerror_log.txt
│   │   └── timeout_log.txt
│   └── sample_complaints/         # Sample customer messages for demo
│       └── complaints.json
│
├── frontend/
│   └── app.py                     # Streamlit dashboard
│
├── tests/
│   └── test_agents.py
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## 6. State Schema (LangGraph)

Define a shared state object that all agents read from and write to:

```python
from typing import TypedDict, List, Optional

class IncidentState(TypedDict):
    # Inputs
    raw_complaints: List[str]          # Customer messages
    raw_logs: str                      # Error logs / stack trace

    # Correlation Agent output
    correlated_error: str              # Linked complaint-to-error summary
    affected_customers: List[str]      # List of affected customer IDs/names

    # Root Cause Agent output
    root_cause: str                    # Root cause hypothesis
    relevant_files: List[str]          # Files likely involved

    # Fix Generator output
    code_patch: str                    # The proposed fix
    patch_explanation: str             # Human-readable explanation

    # Execution Agent output
    test_results: str                  # stdout/stderr from test run
    tests_passed: bool                 # True/False

    # Critic Agent output
    retry_count: int                   # Number of fix attempts
    critic_feedback: str               # Why fix failed, what to change

    # Customer Response Agent output
    customer_replies: List[str]        # Draft messages per customer

    # Incident Report Agent output
    postmortem_report: str             # Full markdown postmortem

    # Control
    escalate_to_human: bool            # True if max retries exceeded
    status: str                        # Current pipeline status
```

---

## 7. Agent Implementation Details

### 7.1 Correlation Agent

**Purpose:** Match customer complaints to specific error logs.

**Prompt guidance:**
- Input: raw complaint messages + raw error logs
- Output: structured summary linking which complaints relate to which error, extract affected customer names/IDs, identify error type and location

**Key logic:**
```python
def correlation_agent(state: IncidentState) -> IncidentState:
    # Call LLM with complaints + logs
    # Extract: error type, affected users, file/line reference
    # Update state with correlated_error and affected_customers
```

---

### 7.2 Root Cause Agent (RAG-enabled)

**Purpose:** Diagnose the root cause using correlated error + retrieved past incidents.

**RAG retrieval:**
- Query ChromaDB with the correlated error summary
- Retrieve top 3 similar past incidents
- Include retrieved context in LLM prompt

**Prompt guidance:**
- Input: correlated error + retrieved past incidents + code snippets (if available)
- Output: root cause hypothesis + list of files likely involved

```python
def root_cause_agent(state: IncidentState) -> IncidentState:
    context = vectorstore.query(state["correlated_error"], top_k=3)
    # Call LLM with error + context
    # Output root_cause and relevant_files
```

---

### 7.3 Fix Generator Agent

**Purpose:** Generate a code patch based on root cause.

**Prompt guidance:**
- Input: root cause + relevant file contents + past fixes (from RAG)
- Output: exact code patch (unified diff format preferred) + plain English explanation

**Important:** Instruct the LLM to output the fix in a parseable format:
```
FILE: data_processing.py
LINE: 42
FIX:
```python
# before
items[index]
# after
items[index] if index < len(items) else None
```
```

---

### 7.4 Execution Agent

**Purpose:** Apply the patch and run tests in a safe sandbox.

**Implementation:**
```python
def execution_agent(state: IncidentState) -> IncidentState:
    # 1. Write patched code to temp file
    # 2. Run in Docker container (or subprocess with timeout)
    # 3. Execute pytest on relevant test files
    # 4. Capture stdout/stderr
    # 5. Set tests_passed = True/False
```

**Docker command:**
```bash
docker run --rm -v /tmp/patch:/app python:3.11 bash -c "cd /app && pip install -r requirements.txt -q && pytest tests/ -v"
```

**Fallback (no Docker):** Use `subprocess.run` with `timeout=30`.

---

### 7.5 Critic Agent

**Purpose:** When tests fail, analyze why and give targeted feedback to Fix Generator.

**Prompt guidance:**
- Input: original root cause + code patch that failed + test failure output
- Output: specific critique — what was wrong, what the next fix attempt should focus on

**Loop control:**
```python
def should_retry(state: IncidentState) -> str:
    if state["tests_passed"]:
        return "customer_response"
    elif state["retry_count"] >= 3:
        return "escalate"
    else:
        return "fix_generator"  # loop back
```

---

### 7.6 Customer Response Agent

**Purpose:** Draft personalized, empathetic replies to each affected customer.

**Prompt guidance:**
- Input: root cause (simplified) + list of affected customers + fix status
- Output: one reply per customer — acknowledge the issue, explain briefly, confirm resolution

**Example output:**
```
To: john@example.com
Hi John, we identified and resolved the issue that caused your error at 2:34 PM.
The problem was in our data processing pipeline. Your request has been reprocessed
successfully. We apologize for the inconvenience.
```

---

### 7.7 Incident Report Agent

**Purpose:** Generate a complete postmortem markdown document.

**Report structure:**
```markdown
# Incident Report — [timestamp]

## Summary
Brief description of what happened.

## Timeline
- HH:MM - First complaint received
- HH:MM - Error detected in logs
- HH:MM - Root cause identified
- HH:MM - Fix generated and validated
- HH:MM - Customers notified

## Root Cause
[Detailed explanation]

## Fix Applied
[Code patch with explanation]

## Customers Affected
[List]

## Prevention
[Recommendations to prevent recurrence]
```

---

## 8. LangGraph Workflow Definition

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(IncidentState)

# Add nodes
workflow.add_node("correlation", correlation_agent)
workflow.add_node("root_cause", root_cause_agent)
workflow.add_node("fix_generator", fix_generator_agent)
workflow.add_node("execution", execution_agent)
workflow.add_node("critic", critic_agent)
workflow.add_node("customer_response", customer_response_agent)
workflow.add_node("incident_report", incident_report_agent)

# Define edges
workflow.set_entry_point("correlation")
workflow.add_edge("correlation", "root_cause")
workflow.add_edge("root_cause", "fix_generator")
workflow.add_edge("fix_generator", "execution")

# Conditional edge — retry loop
workflow.add_conditional_edges(
    "execution",
    should_retry,
    {
        "customer_response": "customer_response",
        "fix_generator": "critic",
        "escalate": END
    }
)
workflow.add_edge("critic", "fix_generator")
workflow.add_edge("customer_response", "incident_report")
workflow.add_edge("incident_report", END)

app = workflow.compile()
```

---

## 9. RAG Setup

### 9.1 Ingestion

Store past incidents as markdown files in `rag/past_incidents/`. Each file should follow:
```markdown
# Incident: IndexError in data_processing.py
**Date:** 2024-11-15
**Error:** IndexError: list index out of range at line 42
**Root Cause:** Missing bounds check before list access
**Fix:** Added `if index < len(items)` guard
**Outcome:** Resolved in 12 minutes
```

### 9.2 ChromaDB Setup

```python
import chromadb
from sentence_transformers import SentenceTransformer

client = chromadb.Client()
collection = client.create_collection("past_incidents")

# Ingest
for doc in past_incident_docs:
    embedding = model.encode(doc["content"])
    collection.add(documents=[doc["content"]], embeddings=[embedding], ids=[doc["id"]])

# Query
def retrieve_context(query: str, top_k: int = 3):
    query_embedding = model.encode(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    return results["documents"][0]
```

---

## 10. Streamlit Dashboard (frontend/app.py)

### Layout

```
┌─────────────────────────────────────────────────────┐
│  🚨 Production Incident Response System              │
├────────────────────┬────────────────────────────────┤
│  INPUT             │  AGENT ACTIVITY (live feed)     │
│  ─────────────     │  ──────────────────────────     │
│  [Error Logs]      │  ✅ Correlation Agent — done    │
│  (text area)       │  ✅ Root Cause Agent — done     │
│                    │  🔄 Fix Generator — running...  │
│  [Customer         │  ⏳ Execution Agent — waiting   │
│   Complaints]      │  ⏳ Critic Agent — waiting      │
│  (text area)       │                                 │
│                    │                                 │
│  [▶ Run System]    │                                 │
├────────────────────┴────────────────────────────────┤
│  OUTPUT TABS                                         │
│  [Root Cause] [Fix Applied] [Customer Replies]       │
│  [Postmortem Report] [Timeline]                      │
└─────────────────────────────────────────────────────┘
```

### Key Streamlit features to implement:
- `st.status()` for live agent activity feed
- `st.tabs()` for organized output sections
- `st.code()` for displaying code patches with syntax highlighting
- `st.download_button()` for downloading postmortem report
- `st.metric()` for showing: time to resolution, retry count, customers affected

---

## 11. Demo Script (for interviews/README)

**Input:**
```
Error Log:
  Traceback (most recent call last):
    File "data_processing.py", line 42, in process_batch
      result = items[index]
  IndexError: list index out of range

Customer Complaints:
  - "Your app keeps crashing when I upload my file!" — Alice
  - "Getting an error every time I submit" — Bob
  - "App is broken, please fix!" — Charlie
```

**Expected Output Flow:**
1. Correlation Agent links all 3 complaints to the IndexError at line 42
2. Root Cause Agent identifies missing bounds check, retrieves similar past incident
3. Fix Generator adds `if index < len(items)` guard
4. Execution Agent runs pytest — all tests pass ✅
5. Customer Response Agent drafts 3 personalized apology messages
6. Incident Report Agent generates full postmortem

**Total time: ~15-20 seconds**

---

## 12. Requirements

```
# requirements.txt
langgraph>=0.2.0
langchain>=0.3.0
langchain-groq>=0.2.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
streamlit>=1.38.0
PyGithub>=2.3.0
python-dotenv>=1.0.0
pytest>=8.0.0
docker>=7.0.0
```

---

## 13. Environment Variables

```
# .env.example
GROQ_API_KEY=your_groq_api_key_here
GITHUB_TOKEN=your_github_token_here  # optional
CHROMA_PERSIST_DIR=./rag/chroma_db
MAX_RETRY_ATTEMPTS=3
LLM_MODEL=llama-3.1-70b-versatile
```

---

## 14. Implementation Order (Recommended)

Build in this sequence to have a working demo at each step:

1. **Set up project structure** — folders, requirements, .env
2. **Set up RAG** — ingest sample past incidents into ChromaDB
3. **Build LangGraph state + workflow skeleton** — nodes with placeholder functions
4. **Implement Correlation Agent** — test with sample data
5. **Implement Root Cause Agent** — connect RAG retrieval
6. **Implement Fix Generator Agent** — test with sample stack trace
7. **Implement Execution Agent** — start with subprocess, add Docker later
8. **Implement Critic Agent + retry loop** — test the full loop
9. **Implement Customer Response Agent**
10. **Implement Incident Report Agent**
11. **Build Streamlit dashboard**
12. **End-to-end demo test** with 3 different sample incidents
13. **Polish README** with demo GIF and architecture diagram

---

## 15. Stretch Goals (add after core works)

- **Slack/email integration** — actually send customer replies via SendGrid or Slack webhook
- **GitHub integration** — auto-create a PR with the fix using PyGithub
- **Monitoring dashboard** — track resolution time, retry counts, agent latency over multiple incidents
- **Multi-language support** — handle Python, JavaScript, and Java stack traces
- **Severity classification** — P0/P1/P2 tagging based on number of affected customers

---

## 16. Key Talking Points for Interviews

- **Why multi-agent?** Each agent has a single responsibility. A monolithic LLM call can't reliably correlate + diagnose + fix + validate + communicate in one shot.
- **Why the retry loop?** Production AI systems need to handle failure gracefully. The self-healing loop is what separates a demo from a real system.
- **Why RAG?** Past incidents are the most valuable context for diagnosing new ones. We don't want the LLM to guess — we want it to learn from history.
- **Tradeoff made:** We chose Groq (free, fast) over GPT-4 — acceptable for this use case because Llama 70B handles code reasoning well and latency matters for incident response.
- **What would you add in production?** Human-in-the-loop approval before applying patches, integration with PagerDuty for alerting, and persistent incident history in a proper database.
