"""Validate pinned held-out manifests that use either upstream test root spelling."""

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from tests.benchmark.real.manifest import Bug, safe_path


@dataclass(frozen=True)
class HeldOutBug(Bug):
    def __post_init__(self):
        test = safe_path(self.test_file)
        if "tests" in test.parts:
            super().__post_init__()
            return
        if "test" not in test.parts:
            raise ValueError(f"{self.id}: expected a test or tests directory.")
        depth = test.parts.index("test")
        root = PurePosixPath(*test.parts[:depth + 1])

        def project(path: str) -> str:
            relative = safe_path(path).relative_to(root)
            return PurePosixPath(*root.parts[:-1], "tests", relative).as_posix()

        if safe_path(self.source_path).is_relative_to(root):
            raise ValueError(f"{self.id}: source must be outside the test directory.")
        surrogate = project(self.test_file)

        def project_node(node: str) -> str:
            path, marker, name = node.partition("::")
            return project(path) + marker + name

        Bug(**{
            **asdict(self),
            "test_file": surrogate,
            "oracle_files": tuple(map(project, self.oracle_files)),
            "fail_to_pass": tuple(map(project_node, self.fail_to_pass)),
            "pass_to_pass": tuple(map(project_node, self.pass_to_pass)),
        })
