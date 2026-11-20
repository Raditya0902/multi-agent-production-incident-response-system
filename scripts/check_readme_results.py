"""Check that README evaluation tables agree with their evidence tables."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("synthetic", "development", "held-out")
MARKED_TABLE = re.compile(
    r"^<!-- evaluation:([a-z-]+) -->\n(.*?)^<!-- /evaluation -->$",
    re.MULTILINE | re.DOTALL,
)


def _table_cells(body: str) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in body.splitlines()
        if line.strip()
    )


def check(readme: str, evidence: Path) -> list[str]:
    _, heading, rest = readme.partition("\n## Evaluation\n")
    if not heading:
        return ["README is missing its Evaluation section."]
    section = re.split(r"^## ", rest, maxsplit=1, flags=re.MULTILINE)[0]
    blocks = MARKED_TABLE.findall(section)
    if sorted(name for name, _ in blocks) != sorted(SUITES):
        return ["README must contain one marked results table for each evaluation suite."]
    errors = []
    if re.search(r"^\s*\|", MARKED_TABLE.sub("", section), re.MULTILINE):
        errors.append("An unmarked table in README Evaluation has no evidence check.")
    for suite, body in blocks:
        path = evidence / f"{suite}.md"
        expected = [
            source for name, source in MARKED_TABLE.findall(path.read_text(encoding="utf-8"))
            if name == suite
        ]
        if len(expected) != 1 or _table_cells(body) != _table_cells(expected[0]):
            errors.append(f"README table for {suite} differs from {path.name}.")
    return errors


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    errors = check(readme, ROOT / "docs" / "evaluation")
    if errors:
        print("\n".join(errors))
        return 1
    print("README results match all three evaluation reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
