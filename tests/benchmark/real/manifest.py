"""Pinned inputs for the BugsInPy benchmark."""

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath


DATASET = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
MANIFESTS = Path(__file__).with_name("manifests")
IMAGE = "incident-real-benchmark:stage-a"
COMMIT = re.compile(r"[0-9a-f]{40}")


def safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or "\\" in value or path.as_posix() != value
            or any(part in {".", "..", ".git"} for part in path.parts)):
        raise ValueError(f"Expected a canonical repository-relative path: {value!r}")
    return path


@dataclass(frozen=True)
class Bug:
    id: str
    repository: str
    buggy_commit: str
    fixed_commit: str
    source_path: str
    test_file: str
    oracle_files: tuple[str, ...]
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]

    @property
    def project(self) -> str:
        return self.id.rsplit("-", 1)[0]

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z][\w-]*-[1-9][0-9]*", self.id):
            raise ValueError(f"Invalid BugsInPy ID: {self.id}")
        if not re.fullmatch(r"https://github\.com/[\w-]+/[\w.-]+", self.repository):
            raise ValueError(f"{self.id}: expected a public GitHub repository.")
        if any(not COMMIT.fullmatch(ref) for ref in (self.buggy_commit, self.fixed_commit)):
            raise ValueError(f"{self.id}: source revisions must be full Git commit hashes.")
        source = safe_path(self.source_path)
        test = safe_path(self.test_file)
        if source.suffix != ".py" or test.suffix != ".py" or "tests" in source.parts or "tests" not in test.parts:
            raise ValueError(f"{self.id}: expected distinct Python source and test files.")
        test_root = PurePosixPath(*test.parts[:test.parts.index("tests") + 1])
        for file in self.oracle_files:
            path = safe_path(file)
            if not path.is_relative_to(test_root) or path == source:
                raise ValueError(f"{self.id}: oracle files must stay in the test tree.")
        nodes = (*self.fail_to_pass, *self.pass_to_pass)
        if not self.fail_to_pass or len(set(nodes)) != len(nodes):
            raise ValueError(f"{self.id}: regression test IDs must be present and unique.")
        if any(not node.startswith(f"{test}::") for node in nodes):
            raise ValueError(f"{self.id}: all test IDs must belong to {test}.")

    @classmethod
    def read(cls, path: Path):
        values = json.loads(path.read_text(encoding="utf-8"))
        if values.pop("bugsinpy_commit") != DATASET:
            raise ValueError(f"{path}: unexpected BugsInPy revision.")
        for key in ("oracle_files", "fail_to_pass", "pass_to_pass"):
            values[key] = tuple(values[key])
        bug = cls(**values)
        if not bug.pass_to_pass or path.stem != bug.id:
            raise ValueError(f"{path}: missing pass-to-pass tests or inconsistent ID.")
        return bug

    def to_dict(self):
        return {"bugsinpy_commit": DATASET, **{field.name: getattr(self, field.name) for field in fields(self)}}
