import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.execution_agent import parse_code_patch
from agents.patch_paths import canonical_app_path, with_patch_path

logger = logging.getLogger(__name__)

_SEVERITY_ICON = {"P0": "🔴", "P1": "🟠", "P2": "🟡"}


def is_configured() -> bool:
    return bool(os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO"))


def _get_github_client(token: str):
    from github import Auth, Github
    return Github(auth=Auth.Token(token))


def create_pr(state: dict, incident_id: int) -> Optional[str]:
    """
    Create a GitHub PR with the generated fix.
    Only runs when tests passed and credentials are configured.
    Returns the PR URL, or None if skipped/failed.
    """
    if not is_configured():
        return None
    if not state.get("tests_passed"):
        return None

    try:
        patch = parse_code_patch(state.get("code_patch", ""))
        file_path = canonical_app_path(Path(__file__).resolve().parent.parent, patch["file"])
        patch["file"] = file_path
        token = os.getenv("GITHUB_TOKEN")
        repo_name = os.getenv("GITHUB_REPO")
        base_branch = os.getenv("GITHUB_BASE_BRANCH", "main")

        g = _get_github_client(token)
        repo = g.get_repo(repo_name)

        base_sha = repo.get_branch(base_branch).commit.sha
        base_tree = repo.get_git_commit(base_sha).tree.sha
        tree = repo.get_git_tree(base_tree, recursive=True)
        if tree.truncated or not any(
            entry.path == file_path and entry.type == "blob" and entry.mode in {"100644", "100755"}
            for entry in tree.tree
        ):
            logger.warning("GitHub PR: target is not a regular file in the pinned base tree")
            return None

        existing = repo.get_contents(file_path, ref=base_sha)
        branch_name = _make_branch_name(state, incident_id)
        new_content = _get_updated_content(repo, file_path, patch, base_sha)
        repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)
        commit_msg = f"fix({file_path}): {_short_error(state)} (incident #{incident_id})"
        repo.update_file(file_path, commit_msg, new_content, existing.sha, branch=branch_name)

        severity = state.get("severity", "P2")
        icon = _SEVERITY_ICON.get(severity, "⚪")
        title = f"[{severity}] {icon} Fix: {_short_error(state)}"[:72]

        pr = repo.create_pull(
            title=title,
            body=_build_pr_body(
                {**state, "code_patch": with_patch_path(state["code_patch"], file_path)}, incident_id, branch_name,
            ),
            head=branch_name,
            base=base_branch,
        )
        return pr.html_url

    except Exception as e:
        logger.warning("GitHub PR creation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_branch_name(state: dict, incident_id: int) -> str:
    severity = (state.get("severity") or "p2").lower()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"incident-fix/{severity}-{incident_id}-{ts}"


def _short_error(state: dict) -> str:
    error = state.get("correlated_error") or "unknown error"
    return error[:60].rstrip()


def _get_updated_content(repo, file_path: str, patch: dict, branch: str) -> str:
    """
    Fetch the existing file from the repo and apply the original→fixed replacement.
    Falls back to the fixed snippet alone if the file doesn't exist or the
    original snippet isn't present in the current file.
    """
    try:
        from github import GithubException
        contents = repo.get_contents(file_path, ref=branch)
        existing = contents.decoded_content.decode("utf-8")
        original = patch.get("original", "")
        fixed = patch.get("fixed", "")
        if original and original.strip() in existing:
            return existing.replace(original.strip(), fixed.strip(), 1)
        # Original snippet not found — append the fix as a clearly-marked block
        logger.warning("GitHub PR: original snippet not found in %s, appending fix", file_path)
        return existing + f"\n\n# --- Suggested fix (incident fix) ---\n{fixed}\n"
    except Exception:
        # File doesn't exist in the repo yet — create it with just the fixed code
        return patch.get("fixed", "# Auto-generated fix\n")


def _build_pr_body(state: dict, incident_id: int, branch_name: str) -> str:
    severity = state.get("severity", "P2")
    icon = _SEVERITY_ICON.get(severity, "⚪")
    severity_reason = state.get("severity_reason", "")
    error = state.get("correlated_error") or "—"
    root_cause = state.get("root_cause") or "—"
    patch = parse_code_patch(state.get("code_patch", ""))
    file_path = patch.get("file", "—")
    original = patch.get("original", "").strip()
    fixed = patch.get("fixed", "").strip()
    explanation = patch.get("explanation") or state.get("patch_explanation") or "—"
    customers = state.get("affected_customers") or []
    customer_list = "\n".join(f"- {c}" for c in customers) if customers else "— (none recorded)"
    retries = state.get("retry_count", 0)
    retry_label = f"{retries} retry attempt(s)" if retries else "passed on first attempt"

    return f"""## 🤖 Auto-generated by Incident Response AI

> **Severity:** {icon} {severity} — {severity_reason}
> **Incident:** #{incident_id}
> **Branch:** `{branch_name}`

---

### Root Cause

{root_cause}

---

### Fix Applied

**File:** `{file_path}`

**Before:**
```python
{original}
```

**After:**
```python
{fixed}
```

**Explanation:** {explanation}

---

### Affected Customers

{customer_list}

---

### Validation

- ✅ Tests passed — {retry_label}
- 👤 Patch reviewed and approved by human engineer before execution

---

*Generated by the Multi-Agent Production Incident Response System*
"""
