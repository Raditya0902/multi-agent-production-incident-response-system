from agents.source_context import anchor_feedback, matching_blocks, source_windows


def test_window_reconciles_incident_line_and_preserves_indentation():
    lines = ["# pad"] * 40
    lines[19:21] = ["def compute():", "    return numerator / denominator"]
    logs = '\n'.join([
        '  File "/app/module.py", line 91, in compute',
        "    return numerator / denominator",
    ])
    windows = source_windows(logs, lambda path: "\n".join(lines), mount="/app", prefix="app/")
    window, = windows
    assert (window.path, window.first, window.last) == ("app/module.py", 11, 31)
    assert "def compute():\n    return numerator / denominator" in window.body


def test_windows_never_read_test_paths_or_unknown_absolute_paths():
    logs = (
        'File "/app/tests/test_private.py", line 1\n    call()\n'
        'File "pkg/test/test_private.py", line 1\n    call()\n'
        'File "pkg/conftest.py", line 1\n    call()\n'
        'File "TESTS/BENCHMARK/REFERENCE_FIXES/module.py", line 1\n    call()\n'
        'File "pkg/TEST_private.py", line 1\n    call()\n'
        'File "/outside/module.py", line 1\n    call()\n'
    )

    def read(path):
        raise AssertionError(path)

    assert not source_windows(logs, read, mount="/app", prefix="app/")


def test_anchor_feedback_reports_zero_and_multiple_matches():
    source = "def main():\n    compute()\n    compute()\n"
    logs = 'File "module.py", line 2, in main\n    compute()'
    read = lambda _: source
    windows = source_windows(logs, read)
    detail = "ORIGINAL must match exactly one source block."
    for original, count in [("    invented()", 0), ("    compute()", 2)]:
        assert matching_blocks(source, original) == count
        feedback = anchor_feedback({"file": "module.py"}, original, windows, read, detail)
        assert f"matched {count} source blocks" in feedback
        assert "def main():" in feedback
    assert not anchor_feedback({"file": "unknown.py"}, "call()", windows, read, detail)
