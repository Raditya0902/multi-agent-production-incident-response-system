# Visual Assets

This directory holds screenshots and GIFs for the project README and demo docs. The files listed below do not exist yet — capture them during a live demo run and save them here.

---

## Asset List

| File | What it shows |
|---|---|
| `demo.gif` | Full end-to-end demo: paste logs → approve patch → tests pass → PR created |
| `architecture.png` | The Mermaid pipeline diagram exported as a static image |
| `agent-flow.png` | Agent dependency graph or flow diagram |
| `hitl-gate.png` | The HITL approval screen showing the confidence score and unified diff |
| `tests-passed.png` | Execution Agent panel showing pytest output and "2 passed" result |
| `github-pr.png` | Auto-generated GitHub PR with patch applied to the source file |
| `slack-notification.png` | Block Kit Slack message in the `#incidents` channel |
| `analytics-dashboard.png` | Analytics page showing severity breakdown, MTTR trends, and retry distribution |

---

## Capture Instructions

### demo.gif

1. Open a screen recorder (macOS: [Kap](https://getkap.co/) or QuickTime; Linux: [Peek](https://github.com/phw/peek) or `ffmpeg`).
2. Set the capture area to the Streamlit window at `http://localhost:8501`.
3. Record a full run using Scenario 1 from `test_cases.txt` (paste → run → approve → result).
4. Keep it under 90 seconds. Export as GIF at ≤ 15fps, ≤ 10MB.

### hitl-gate.png

1. Run Phase 1 with Scenario 1.
2. When the pipeline pauses at the approval gate, take a screenshot of the full Streamlit window.
3. Crop to show the severity badge, confidence score, unified diff, and Approve/Reject buttons.

### tests-passed.png

1. After approving at the HITL gate, wait for Phase 2 to complete.
2. Screenshot the Execution Agent result panel showing the pytest output (`2 passed in X.Xs`).

### github-pr.png

1. Set `GITHUB_TOKEN` and `GITHUB_REPO` in `.env`.
2. Complete a full run with Scenario 1.
3. Open the auto-created PR on GitHub and screenshot the PR page showing the title, patch diff, and test results in the PR body.

### slack-notification.png

1. Set `SLACK_BOT_TOKEN` and `SLACK_INCIDENT_CHANNEL` in `.env`.
2. Complete a full run.
3. Open Slack and screenshot the Block Kit message in the incidents channel.

### analytics-dashboard.png

1. Run at least 3 different benchmark scenarios to populate the Analytics page.
2. Navigate to `http://localhost:8501/Analytics`.
3. Screenshot the full page with the Plotly charts visible.

### architecture.png

1. Copy the Mermaid diagram source from `README.md`.
2. Paste into [mermaid.live](https://mermaid.live/) and export as PNG at 2x resolution.
3. Save as `docs/assets/architecture.png`.

### agent-flow.png

Option A: Export the architecture.png diagram (same as above, cropped to Phase 1/Phase 2 subgraphs).

Option B: Draw a custom agent dependency graph showing:
- IncidentState as the central shared object
- Arrows from each agent to the fields it produces
- The retry loop between Execution → Critic → Fix Generator
