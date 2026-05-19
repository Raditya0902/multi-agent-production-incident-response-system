# Demo Walkthrough

A recommended script for a 60–90 second live demo of the system. Use **Scenario 1** (IndexError — file upload crash) from `test_cases.txt` for the most reliable demo path.

---

## Prerequisites

1. `GROQ_API_KEY` set in `.env`
2. RAG knowledge base initialized: `python -m rag.ingestion`
3. Dashboard running: `streamlit run frontend/app.py`
4. Optional (for side effects): `SLACK_BOT_TOKEN`, `GITHUB_TOKEN`, `GITHUB_REPO` in `.env`

---

## Demo Script (60–90 seconds)

### Step 1 — Paste logs and complaints (10s)

Open `test_cases.txt` and copy the Scenario 1 block.

Paste into the **Logs** text area and **Customer Complaints** text area on the dashboard. Point out:
- The stack trace shows `IndexError: list index out of range` at `data_processing.py:42`
- Two customers are affected

### Step 2 — Click Run (2s)

Click the **Run** button. Phase 1 begins automatically.

### Step 3 — Watch Phase 1 stream (15–25s)

Point out each agent as it completes (shown in the activity panel):
- **Correlation Agent** → identifies the error and customer names
- **Severity Agent** → assigns P2 with a reason
- **Root Cause Agent** → retrieves similar past incidents from ChromaDB, diagnoses the missing bounds check
- **Fix Generator** → generates the patch

### Step 4 — Review the HITL approval gate (10s)

The pipeline pauses. Show:
- Severity badge and **confidence score** (typically ≥ 0.9 for this scenario)
- The **unified diff view** showing `+ if not items: return []` added to `data_processing.py`
- Approve and Reject buttons

### Step 5 — Approve the patch (2s)

Click **Approve**. Phase 2 begins.

### Step 6 — Watch tests pass (10–15s)

The Execution Agent:
- Finds the real pytest file (`tests/test_data_processing.py`)
- Runs it in a subprocess sandbox
- Reports `2 passed` — no retry needed

### Step 7 — Show the postmortem (5s)

Scroll to the **Incident Report** section. Show the auto-generated Markdown postmortem with timeline, root cause, fix summary, and recommendations.

### Step 8 — Show the Slack notification (5s)

If Slack is configured, open the `#incidents` channel. Show the Block Kit message with severity color, root cause, affected customers, and GitHub PR link.

### Step 9 — Show the GitHub PR (5s)

If GitHub is configured, open the automatically created PR. Show:
- Branch name (`fix/data_processing-indexerror-<timestamp>`)
- Patch applied to `app/data_processing.py`
- PR body with root cause, patch diff, and test results

---

## Visual Assets

### HITL Approval Gate
![HITL approval gate](assets/hitl-gate.png)

### Tests Passing in Sandbox
![Tests passed](assets/tests-passed.png)

### Auto-Generated GitHub PR
![GitHub PR](assets/github-pr.png)

### Slack Notification
![Slack notification](assets/slack-notification.png)

### Analytics Dashboard
![Analytics dashboard](assets/analytics-dashboard.png)

> Add `docs/assets/demo.gif` (screen recording of a full run) when available. See [`docs/assets/README.md`](assets/README.md) for capture instructions.

---

## Retry Path Demo (optional, adds ~30s)

To demonstrate the self-healing retry loop, use **Scenario 7** (Reject → regenerate flow) from `test_cases.txt`:

1. Run through Phase 1 as above.
2. At the HITL gate, click **Reject** and enter feedback: `"The fix must handle the empty list case before the while loop."`
3. The Fix Generator regenerates the patch with the feedback injected.
4. Review the updated patch and approve it.
5. Phase 2 runs normally.

This demonstrates the human feedback mechanism without waiting for an actual test failure.
