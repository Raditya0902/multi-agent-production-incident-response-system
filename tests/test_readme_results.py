from scripts.check_readme_results import ROOT, check


def test_readme_tables_match_evaluation_and_reject_changed_numbers():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    evidence = ROOT / "docs" / "evaluation"
    assert check(readme, evidence) == []

    marker = "| Distinct cases resolved | 1/12 (8.3%) | 3/12 (25.0%) |"
    assert marker in readme
    changed = readme.replace(marker, marker.replace("3/12", "4/12"), 1)
    assert check(changed, evidence) == ["README table for held-out differs from held-out.md."]


def test_readme_rejects_unchecked_tables():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changed = readme.replace(
        "### Synthetic regression suite",
        "| Unchecked metric | Value |\n| --- | --- |\n| Unknown | 100% |\n\n"
        "### Synthetic regression suite",
        1,
    )
    assert check(changed, ROOT / "docs" / "evaluation") == [
        "An unmarked table in README Evaluation has no evidence check."
    ]
