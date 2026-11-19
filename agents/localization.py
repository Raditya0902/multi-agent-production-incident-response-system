"""Rank source locations observed in incident frames and repository call paths."""

from collections.abc import Callable
from pathlib import PurePosixPath

from agents.source_context import FRAME, trace_path

MAX_CANDIDATES = 4


def ranked_locations(logs: str, read: Callable[[str], str | None], **aliases) -> dict[str, str]:
    matches = list(FRAME.finditer(logs))
    direct = [match for match in matches if match["kind"] == "File"]
    calls = [match for match in matches if match["kind"].startswith("Followed call")]
    entries = [match for match in matches if match["kind"].startswith("Observed call")]
    groups = (
        (reversed(direct), "failure frame"),
        (calls, "repository call followed from an entry point"),
        (reversed(entries), "observed entry point"),
    )
    locations = {}
    for frames, evidence in groups:
        for frame in frames:
            path = trace_path(frame["path"], **aliases)
            if path and path not in locations and read(path):
                locations[path] = f"{path}:{frame['line']} — {evidence}"
                if len(locations) == MAX_CANDIDATES:
                    return locations
    return locations


def file_retry_feedback(rejected: set[str], ranked: dict[str, str]) -> str:
    remaining = [
        description for path, description in ranked.items()
        if path not in rejected and PurePosixPath(path).name not in rejected
    ]
    if not remaining:
        return ""
    return (
        "The last file was rejected. Recheck which production frame owns the failing behavior. "
        "Other observed source locations:\n" + "\n".join(remaining)
    )
