"""Project evaluator results into feedback that contains no test oracle text."""

import re

_SUMMARY = re.compile(r"^(?:=+ )?((?:\d+ [a-z]+(?:, )?)+) in \d+(?:\.\d+)?s(?: =+)?$", re.MULTILINE)


def service_counts(detail: str) -> str:
    summaries = _SUMMARY.findall(detail)
    if not summaries:
        return "The service checks did not produce a summary."
    summary = summaries[-1]
    counts = {label: int(count) for count, label in re.findall(r"(\d+) (passed|failed)", summary)}
    return f"Service checks: {counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed."


def behavior_counts(verdicts: dict, regressions: tuple[str, ...], controls: tuple[str, ...]) -> str:
    def counts(nodes):
        passed = sum(verdicts.get(node) == "passed" for node in nodes)
        failed = sum(verdicts.get(node) == "failed" for node in nodes)
        return f"{passed} passed, {failed} failed"

    return (
        f"Regression checks: {counts(regressions)}. "
        f"Previously passing checks: {counts(controls)}."
    )
