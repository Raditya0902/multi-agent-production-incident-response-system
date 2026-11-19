"""Atomic per-bug, per-trial results keyed by the benchmark configuration."""

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def fingerprint(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:20]


class TrialCache:
    def __init__(self, directory: Path, configuration: dict):
        self.directory = directory / fingerprint(configuration)

    def path(self, bug_id: str, trial: int) -> Path:
        return self.directory / bug_id / f"trial-{trial}.json"

    def read(self, bug_id: str, trial: int) -> dict | None:
        try:
            return json.loads(self.path(bug_id, trial).read_text())
        except FileNotFoundError:
            return None

    def save(self, bug_id: str, trial: int, result: dict) -> dict:
        path = self.path(bug_id, trial)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(result, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return self.read(bug_id, trial)
        finally:
            temporary.unlink()
        return result
