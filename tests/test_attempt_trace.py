from agents.patch_paths import WORKSPACE_MOUNTS
from agents.source_context import SourceWindow
from tests.benchmark.attempt_trace import AttemptTrace


def test_trace_records_match_counts_and_paths_without_source_or_raw_proposals():
    source = "def main():\n    compute()\n    compute()\n"
    window = SourceWindow("module.py", 1, 3, source.rstrip("\n"), 2)
    trace = AttemptTrace([window], lambda path: source)
    trace.record(
        requested="/workspace/module.py", path="module.py", mounts=WORKSPACE_MOUNTS,
        original="compute()", outcome="patch_fails_to_apply", feedback="anchor_excerpt",
    )
    trace.mark_critic()
    trace.record(
        requested="/host/private/probe.py", path=None, mounts=WORKSPACE_MOUNTS,
        original="hidden()", outcome="wrong_file", feedback="wrong_file",
    )

    records = trace.payload()
    first, second = records["attempts"]
    assert first["original_matches"] == 2
    assert first["path_form"] == "recognized_mount"
    assert first["canonical_path"] == "module.py"
    assert first["feedback_shown_to_critic"] == "anchor_excerpt"
    assert second["path_form"] == "other_absolute"
    assert second["path_decision"] == "rejected"
    assert not second["critic_invoked"]
    assert records["source_windows"][0]["source_lines"] == 3
    assert "compute()" not in str(records)
    assert "/host/private" not in str(records)
