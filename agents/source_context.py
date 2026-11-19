"""Bounded context from the buggy production source available to the incident."""

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

FRAME = re.compile(
    r'^\s*(?:File|Observed call \w+ in) "([^"\n]+)", line (\d+)'
    r'(?:, in ([\w.<>]+))?\n[ \t]+([^\n]+)', re.MULTILINE,
)
NON_SOURCE = {"test", "tests", "testing", "fixtures", "sandbox", "agents", "reference_fixes", "heldout"}
WINDOW_RADIUS = 10
MAX_WINDOWS = 4
MAX_WINDOW_CHARS = 3600


def production_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        path.as_posix() == value and not path.is_absolute() and "\\" not in value
        and path.suffix == ".py" and not path.name.startswith("test_")
        and not path.name.endswith("_test.py") and path.name != "conftest.py"
        and all(not part.startswith(".") and part not in NON_SOURCE for part in path.parts)
    )


def trace_path(value: str, mount: str | None = None, prefix: str = "") -> str | None:
    if mount and value.startswith(mount + "/"):
        value = prefix + value[len(mount) + 1:]
    return value if production_path(value) else None


def read_local_source(root: Path, relative: str) -> str | None:
    if not production_path(relative):
        return None
    path = root / relative
    try:
        if path.resolve(strict=True) == path and path.is_file():
            return path.read_text(encoding="utf-8")
    except (OSError, ValueError, RuntimeError):
        pass
    return None


@dataclass(frozen=True)
class SourceWindow:
    path: str
    first: int
    last: int
    body: str

    def render(self) -> str:
        return f"{self.path}:{self.first}-{self.last}\n```python\n{self.body}\n```"


def source_windows(
    logs: str, read: Callable[[str], str | None], *, mount: str | None = None, prefix: str = "",
) -> list[SourceWindow]:
    windows = []
    source_files = {}
    for frame in reversed(list(FRAME.finditer(logs))):
        path = trace_path(frame[1], mount, prefix)
        if not path:
            continue
        if path not in source_files:
            source_files[path] = (read(path) or "").splitlines()
        lines = source_files[path]
        recorded = frame[4].strip()
        center = int(frame[2]) - 1
        if not 0 <= center < len(lines) or lines[center].strip() != recorded:
            candidates = [index for index, line in enumerate(lines) if line.strip() == recorded]
            if len(candidates) == 1:
                center = candidates[0]
            elif not 0 <= center < len(lines):
                continue
        if any(window.path == path and window.first <= center + 1 <= window.last for window in windows):
            continue
        first = max(0, center - WINDOW_RADIUS)
        end = min(len(lines), center + WINDOW_RADIUS + 1)
        while end > first and len("\n".join(lines[first:end])) > MAX_WINDOW_CHARS:
            if center - first > end - center - 1:
                first += 1
            else:
                end -= 1
        if first <= center < end:
            windows.append(SourceWindow(path, first + 1, end, "\n".join(lines[first:end])))
        if len(windows) == MAX_WINDOWS:
            break
    return windows


def matching_blocks(source: str, original: str) -> int:
    """Count matches for diagnostics using the existing scorer's dedent semantics."""
    expected = textwrap.dedent(original.strip("\r\n")).splitlines()
    if not expected or not original.strip():
        return 0
    lines = source.splitlines(keepends=True)
    length = len(expected)
    return sum(
        textwrap.dedent("".join(lines[start:start + length])).splitlines() == expected
        for start in range(len(lines) - length + 1)
    )


def anchor_feedback(patch: dict, original: str, windows: list[SourceWindow], read, detail: str) -> str:
    if "ORIGINAL must match exactly one source block" not in detail:
        return ""
    candidates = {window.path for window in windows if patch["file"] in {
        window.path, PurePosixPath(window.path).name,
    }}
    if len(candidates) != 1:
        return ""
    path = candidates.pop()
    source = read(path)
    if source is None:
        return ""
    count = matching_blocks(source, original)
    nearest = [window for window in windows if window.path == path][:1]
    if count == 0:
        action = "Copy a contiguous block from the buggy source."
    elif count > 1:
        action = "Include adjacent unchanged lines to select a unique block."
    else:
        return ""
    return f"ORIGINAL matched {count} source blocks. {action}\n" + "\n".join(w.render() for w in nearest)
