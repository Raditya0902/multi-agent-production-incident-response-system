from agents.localization import file_retry_feedback, ranked_locations
from agents.source_context import source_windows


def test_rank_failure_frames_and_observed_dependencies_ahead_of_entry_wrappers():
    logs = (
        'File "outer.py", line 1\n    run()\n'
        'File "inner.py", line 1\n    fail()\n'
        'Observed call entry in "wrapper.py", line 1\n    entry()\n'
        'Followed call work in "core.py", line 1\n    work()\n'
        'Followed call work in "test/private.py", line 1\n    hidden()'
    )
    sources = {"outer.py": "run()", "inner.py": "fail()", "wrapper.py": "entry()", "core.py": "work()"}
    ranked = ranked_locations(logs, sources.get)
    assert list(ranked) == ["inner.py", "outer.py", "core.py", "wrapper.py"]
    assert [window.path for window in source_windows(
        logs, sources.get, ranked_paths=tuple(ranked),
    )] == list(ranked)
    retry = file_retry_feedback({"inner.py", "wrapper.py"}, ranked)
    assert "inner.py" not in retry
    assert "wrapper.py" not in retry
    assert "core.py" in retry
    assert "test/private.py" not in retry
