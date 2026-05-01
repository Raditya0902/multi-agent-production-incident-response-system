import pytest
from notifications.github_pr import (
    is_configured,
    create_pr,
    _make_branch_name,
    _short_error,
    _get_updated_content,
    _build_pr_body,
)

RESOLVED_STATE = {
    "severity": "P1",
    "severity_reason": "Core feature broken for 2 users.",
    "correlated_error": "IndexError: list index out of range in data_processing.py:42",
    "affected_customers": ["Alice Johnson", "Bob Martinez"],
    "relevant_files": ["data_processing.py"],
    "root_cause": "Missing bounds check before list indexing.",
    "code_patch": (
        "===FILE===\ndata_processing.py\n"
        "===ORIGINAL===\nresult = items[index]\n"
        "===FIXED===\nresult = items[index] if index < len(items) else None\n"
        "===EXPLANATION===\nAdded bounds check to handle empty lists."
    ),
    "patch_explanation": "Added bounds check to handle empty lists.",
    "test_results": "4 passed in 0.01s",
    "tests_passed": True,
    "retry_count": 1,
    "escalate_to_human": False,
    "status": "complete",
}

ESCALATED_STATE = {**RESOLVED_STATE, "tests_passed": False, "escalate_to_human": True}


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_not_configured_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    assert is_configured() is False


def test_not_configured_without_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    assert is_configured() is False


def test_configured_with_both(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    assert is_configured() is True


# ---------------------------------------------------------------------------
# create_pr — skips without config or when tests failed
# ---------------------------------------------------------------------------

def test_create_pr_skips_when_not_configured(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    assert create_pr(RESOLVED_STATE, 1) is None


def test_create_pr_skips_when_tests_failed(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    assert create_pr(ESCALATED_STATE, 2) is None


def test_create_pr_returns_none_on_exception(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")

    def bad_client(token):
        raise ConnectionError("network down")

    monkeypatch.setattr("notifications.github_pr._get_github_client", bad_client)
    assert create_pr(RESOLVED_STATE, 1) is None


def test_create_pr_happy_path(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_BASE_BRANCH", "main")

    created_prs = []

    class FakePR:
        html_url = "https://github.com/owner/repo/pull/42"

    class FakeRepo:
        def get_branch(self, name):
            class B:
                class commit:
                    sha = "abc123"
            return B()

        def create_git_ref(self, ref, sha):
            pass

        def get_contents(self, path, ref=None):
            raise Exception("not found")

        def create_file(self, path, msg, content, branch):
            pass

        def create_pull(self, **kwargs):
            created_prs.append(kwargs)
            return FakePR()

    class FakeGithubClient:
        def get_repo(self, name):
            return FakeRepo()

    monkeypatch.setattr("notifications.github_pr._get_github_client", lambda token: FakeGithubClient())

    result = create_pr(RESOLVED_STATE, 7)
    assert result == "https://github.com/owner/repo/pull/42"
    assert len(created_prs) == 1
    assert "[P1]" in created_prs[0]["title"]
    assert "incident-fix/p1-7" in created_prs[0]["head"]


# ---------------------------------------------------------------------------
# _make_branch_name
# ---------------------------------------------------------------------------

def test_branch_name_contains_severity_and_id():
    name = _make_branch_name(RESOLVED_STATE, 5)
    assert name.startswith("incident-fix/p1-5-")


def test_branch_name_contains_timestamp():
    name = _make_branch_name(RESOLVED_STATE, 5)
    # format: incident-fix/p1-5-YYYYMMDD-HHMMSS
    parts = name.split("/")[1].split("-")
    assert len(parts) >= 4


def test_branch_name_lowercase_severity():
    state = {**RESOLVED_STATE, "severity": "P0"}
    name = _make_branch_name(state, 1)
    assert "p0" in name


# ---------------------------------------------------------------------------
# _short_error
# ---------------------------------------------------------------------------

def test_short_error_truncates_at_60():
    state = {"correlated_error": "E" * 100}
    result = _short_error(state)
    assert len(result) <= 60


def test_short_error_uses_correlated_error():
    result = _short_error(RESOLVED_STATE)
    assert "IndexError" in result


def test_short_error_fallback_when_missing():
    result = _short_error({})
    assert result == "unknown error"


# ---------------------------------------------------------------------------
# _get_updated_content
# ---------------------------------------------------------------------------

def test_get_updated_content_applies_patch_when_file_exists():
    patch = {
        "original": "result = items[index]",
        "fixed": "result = items[index] if index < len(items) else None",
        "file": "data_processing.py",
    }

    class FakeContents:
        decoded_content = b"def process(items, index):\n    result = items[index]\n    return result\n"

    class FakeRepo:
        def get_contents(self, path, ref=None):
            return FakeContents()

    content = _get_updated_content(FakeRepo(), "data_processing.py", patch, "branch")
    assert "if index < len(items)" in content
    assert "result = items[index]\n" not in content


def test_get_updated_content_creates_file_when_not_found():
    patch = {
        "original": "result = items[index]",
        "fixed": "result = items[index] if index < len(items) else None",
        "file": "new_module.py",
    }

    class FakeRepo:
        def get_contents(self, path, ref=None):
            raise Exception("404 Not Found")

    content = _get_updated_content(FakeRepo(), "new_module.py", patch, "branch")
    assert "if index < len(items)" in content


def test_get_updated_content_appends_when_original_not_found():
    patch = {
        "original": "some_old_code_not_in_file()",
        "fixed": "the_fixed_code()",
        "file": "data_processing.py",
    }

    class FakeContents:
        decoded_content = b"def process():\n    pass\n"

    class FakeRepo:
        def get_contents(self, path, ref=None):
            return FakeContents()

    content = _get_updated_content(FakeRepo(), "data_processing.py", patch, "branch")
    assert "the_fixed_code()" in content
    assert "def process():" in content  # original file content preserved


# ---------------------------------------------------------------------------
# _build_pr_body
# ---------------------------------------------------------------------------

def test_pr_body_contains_severity():
    body = _build_pr_body(RESOLVED_STATE, 7, "incident-fix/p1-7-20241115")
    assert "P1" in body
    assert "🟠" in body


def test_pr_body_contains_root_cause():
    body = _build_pr_body(RESOLVED_STATE, 7, "incident-fix/p1-7-20241115")
    assert "bounds check" in body


def test_pr_body_contains_before_after():
    body = _build_pr_body(RESOLVED_STATE, 7, "incident-fix/p1-7-20241115")
    assert "result = items[index]" in body
    assert "index < len(items)" in body


def test_pr_body_contains_customers():
    body = _build_pr_body(RESOLVED_STATE, 7, "incident-fix/p1-7-20241115")
    assert "Alice Johnson" in body
    assert "Bob Martinez" in body


def test_pr_body_contains_incident_id():
    body = _build_pr_body(RESOLVED_STATE, 42, "incident-fix/p1-42-20241115")
    assert "#42" in body


def test_pr_body_mentions_human_approval():
    body = _build_pr_body(RESOLVED_STATE, 1, "branch")
    assert "human" in body.lower() or "reviewer" in body.lower()
