"""
Fetch real post-mortems from https://github.com/danluu/post-mortems (public repo).

Uses the GitHub REST API (no auth required for public repos, but sets a
User-Agent to avoid rate limiting). Saves each document as a .md file in
rag/past_incidents/real/ with a YAML frontmatter header.

Usage:
    python -m rag.scripts.fetch_real_postmortems
    python -m rag.scripts.fetch_real_postmortems --max 40
"""

import argparse
import os
import sys
import time
from datetime import date
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
import json

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "past_incidents", "real")
GITHUB_API = "https://api.github.com"
REPO = "danluu/post-mortems"
MIN_WORD_COUNT = 200

_HEADERS = {
    "User-Agent": "incident-response-rag-fetcher/1.0",
    "Accept": "application/vnd.github.v3+json",
}


def _get(url: str) -> dict | list | str:
    req = urllib_request.Request(url, headers=_HEADERS)
    with urllib_request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    # Try JSON, fall back to raw string
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _fetch_file_list() -> list[dict]:
    """Return all files (recursively) from the danluu/post-mortems repo tree."""
    url = f"{GITHUB_API}/repos/{REPO}/git/trees/master?recursive=1"
    data = _get(url)
    return [item for item in data.get("tree", []) if item.get("type") == "blob"]


def _fetch_raw_content(blob_path: str) -> str:
    """Download the raw content of a file via the raw.githubusercontent.com URL."""
    raw_url = f"https://raw.githubusercontent.com/{REPO}/master/{blob_path}"
    req = urllib_request.Request(raw_url, headers={"User-Agent": _HEADERS["User-Agent"]})
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as e:
        print(f"  ⚠ Could not fetch {blob_path}: {e}")
        return ""


def _is_markdown(path: str) -> bool:
    return path.lower().endswith(".md") or path.lower().endswith(".markdown")


def _word_count(text: str) -> int:
    return len(text.split())


def _make_slug(path: str) -> str:
    """Convert a file path to a safe filename slug."""
    name = os.path.basename(path)
    stem, _ = os.path.splitext(name)
    slug = stem.lower().replace(" ", "_").replace("/", "_")
    # Keep only safe characters
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in slug)
    return safe[:80]


def _add_frontmatter(content: str, blob_path: str) -> str:
    blob_url = f"https://github.com/{REPO}/blob/master/{blob_path}"
    today = date.today().isoformat()
    frontmatter = (
        f"---\n"
        f"source: {REPO}\n"
        f"original_url: {blob_url}\n"
        f"fetched_at: {today}\n"
        f"---\n\n"
    )
    # Strip any existing frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip()
    return frontmatter + content


def fetch(max_docs: int = 60) -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Fetching file tree from {REPO}...")
    try:
        files = _fetch_file_list()
    except Exception as e:
        print(f"Error fetching file list: {e}")
        sys.exit(1)

    markdown_files = [f for f in files if _is_markdown(f["path"])]
    print(f"Found {len(markdown_files)} markdown files. Fetching up to {max_docs} with >{MIN_WORD_COUNT} words...")

    saved = 0
    skipped_short = 0
    skipped_existing = 0

    for file_info in markdown_files:
        if saved >= max_docs:
            break

        blob_path = file_info["path"]
        slug = _make_slug(blob_path)
        out_path = os.path.join(OUTPUT_DIR, f"real_{slug}.md")

        if os.path.exists(out_path):
            skipped_existing += 1
            continue

        content = _fetch_raw_content(blob_path)
        if not content or _word_count(content) < MIN_WORD_COUNT:
            skipped_short += 1
            continue

        doc = _add_frontmatter(content, blob_path)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc)

        saved += 1
        print(f"  [{saved}] Saved: {slug}.md ({_word_count(content)} words)")
        # Be polite to the GitHub API
        time.sleep(0.3)

    print(f"\nDone. Saved {saved} documents, skipped {skipped_short} (too short), "
          f"{skipped_existing} already existed.")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch real post-mortems from danluu/post-mortems.")
    parser.add_argument("--max", type=int, default=60, help="Maximum number of documents to fetch (default: 60)")
    args = parser.parse_args()
    fetch(max_docs=args.max)
