from datetime import datetime
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from agents.state import create_initial_state
from db.approval import ApprovalStore


def test_approval_checkpoint_resumes_in_new_dashboard_session(tmp_path, monkeypatch):
    from graph import workflow

    monkeypatch.setenv("HITL_DB_PATH", str(tmp_path / "hitl.db"))
    monkeypatch.setenv("SANDBOX_MODE", "subprocess")
    monkeypatch.setattr("db.history.init_db", lambda: None)
    monkeypatch.setattr("db.history.save_incident", lambda *args: 1)
    monkeypatch.setattr("notifications.slack.notify", lambda *args: False)
    monkeypatch.setattr("notifications.github_pr.create_pr", lambda *args: None)
    calls = []

    def diagnose(state):
        calls.append("diagnose")
        yield {"fix_generator": {"code_patch": "===FILE===\napp/example.py\n"}}

    def execute(state):
        calls.append(state["code_patch"])
        yield {"execution": {"tests_passed": False, "status": "escalated"}}

    monkeypatch.setattr(workflow, "phase1_app", SimpleNamespace(stream=diagnose))
    monkeypatch.setattr(workflow, "phase2_app", SimpleNamespace(stream=execute))
    app = str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")

    first = AppTest.from_file(app).run()
    first.text_area[0].set_value("Example incident log")
    first.text_area[1].set_value("Example complaint")
    first.run()
    next(button for button in first.button if button.label == "Run").click().run()
    assert not first.exception
    run_id = first.session_state["hitl_run_id"]
    assert calls == ["diagnose"]
    assert any("Subprocess sandbox active" in warning.value for warning in first.warning)

    subprocess.run(
        [
            sys.executable, "-B", "-c",
            "from db.approval import ApprovalStore; import sys; "
            "assert ApprovalStore().load(sys.argv[1]).state['raw_logs'] == 'Example incident log'",
            run_id,
        ],
        check=True, timeout=10,
    )
    restarted = AppTest.from_file(app).run()
    restarted.text_input(key="_resume_run_id").set_value(run_id)
    restarted.run()
    next(button for button in restarted.button if button.label == "Resume approval").click().run()
    assert not restarted.exception
    assert restarted.session_state["hitl_phase"] == "awaiting_approval"
    assert restarted.session_state["hitl_state"]["raw_logs"] == "Example incident log"
    assert calls == ["diagnose"]
    next(button for button in restarted.button if button.label == "Approve & Run Tests").click().run()
    assert not restarted.exception
    assert calls == ["diagnose", "===FILE===\napp/example.py\n"]
    assert ApprovalStore().load(run_id) is None


def test_stale_approval_cannot_consume_a_regenerated_patch(tmp_path):
    store = ApprovalStore(tmp_path / "hitl.db")
    state = create_initial_state([], "")
    run_id = store.save(state, {"fix_generator": 1}, datetime.now())
    assert store.revise(run_id, 0, dict(state, code_patch="revised"))
    fresh = ApprovalStore(store.path).load(run_id)
    assert fresh.revision == 1 and fresh.state["code_patch"] == "revised"
    assert not store.consume(run_id, 0)
    assert store.consume(run_id, 1)
    assert not store.consume(run_id, 1)
