"""Record model-attempt evidence without retaining prompts or oracle contents."""

import subprocess
from collections.abc import Callable

from agents.source_context import SourceWindow, matching_blocks


class AttemptTrace:
    def __init__(self, windows: list[SourceWindow], read: Callable[[str], str | None]):
        self.read = read
        self.attempts = []
        self.windows = []
        for window in windows:
            source = read(window.path)
            self.windows.append({
                "path": window.path,
                "first_line": window.first,
                "last_line": window.last,
                "anchor_line": window.anchor,
                "window_bytes": len(window.body.encode("utf-8")),
                "source_lines": len(source.splitlines()) if source else None,
                "source_bytes": len(source.encode("utf-8")) if source else None,
            })

    def record(self, *, requested, path, mounts, original, outcome, feedback):
        if not requested:
            submitted = "empty"
        elif any(requested.startswith(mount + "/") for mount, _ in mounts):
            submitted = "recognized_mount"
        elif requested.startswith("/"):
            submitted = "other_absolute"
        else:
            submitted = "relative"

        matches = None
        if outcome in {"resolved", "wrong_fix"}:
            matches = 1
        elif path and outcome == "patch_fails_to_apply":
            try:
                source = self.read(path)
                if source is not None:
                    matches = matching_blocks(source, original)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                # Diagnostics must not change the evaluator verdict.
                pass

        self.attempts.append({
            "number": len(self.attempts) + 1,
            "path_form": submitted,
            "canonical_path": path,
            "path_decision": (
                "target_rejected" if path and outcome == "wrong_file"
                else "accepted" if path else "rejected"
            ),
            "original_matches": matches,
            "outcome": outcome,
            "feedback_kind": feedback,
            "critic_invoked": False,
            "feedback_shown_to_critic": None,
        })

    def mark_critic(self):
        attempt = self.attempts[-1]
        attempt["critic_invoked"] = True
        attempt["feedback_shown_to_critic"] = attempt["feedback_kind"]

    def payload(self) -> dict:
        return {"source_windows": self.windows, "attempts": self.attempts}
