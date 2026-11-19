"""Canonicalize patch destinations before source reads or writes."""

import re
from pathlib import Path, PurePosixPath

from agents.source_context import production_path

APP_MOUNTS = (("/app/app", "app"), ("/app", "app"))
WORKSPACE_MOUNTS = (("/workspace", ""),)
APP_ROOTS = ("app",)
_FILE_SECTION = re.compile(r"(===FILE===)[^\S\n]*.*?(?====ORIGINAL===)", re.DOTALL)


class PatchPathError(ValueError):
    """A candidate did not identify an unambiguous allowed source file."""


def _relative(value: str, mounts: tuple[tuple[str, str], ...]) -> PurePosixPath:
    if value.startswith("/"):
        for mount, prefix in sorted(mounts, key=lambda mapping: -len(mapping[0])):
            if value.startswith(mount + "/"):
                suffix = value[len(mount) + 1:]
                value = f"{prefix}/{suffix}" if prefix else suffix
                break
        else:
            raise PatchPathError("Unrecognized absolute path.")
    path = PurePosixPath(value)
    if (
        not path.parts or path.as_posix() != value or path.is_absolute()
        or "\\" in value or any(ord(char) < 32 for char in value)
        or ":" in value or ".." in path.parts
    ):
        raise PatchPathError("Path must be canonical and repository-relative.")
    return path


def canonical_patch_path(
    root: Path,
    value: str,
    *,
    mounts: tuple[tuple[str, str], ...] = (),
    bare_root: str | None = None,
    unique_basename: bool = False,
    allowed_roots: tuple[str, ...] = (),
) -> str:
    """Translate known mounts, resolve against the checkout, then allowlist."""
    root = root.resolve(strict=True)
    relative = _relative(value, mounts)
    if len(relative.parts) == 1 and not value.startswith("/"):
        if bare_root is not None:
            relative = PurePosixPath(bare_root) / relative
        elif unique_basename:
            matches = list(root.rglob(relative.name))
            if len(matches) != 1:
                raise PatchPathError("Patch basename does not identify a unique source file.")
            relative = PurePosixPath(matches[0].relative_to(root).as_posix())

    try:
        candidate = (root / relative).resolve(strict=True)
        resolved = candidate.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        raise PatchPathError("Patch path must resolve inside the checkout.") from error

    if (
        not candidate.is_file()
        or not production_path(relative.as_posix())
        or not production_path(resolved)
        or (allowed_roots and not PurePosixPath(resolved).parts[0] in allowed_roots)
    ):
        raise PatchPathError("Patch path is outside the production source allowlist.")
    return resolved


def canonical_app_path(root: Path, value: str) -> str:
    return canonical_patch_path(
        root, value, mounts=APP_MOUNTS, bare_root="app", allowed_roots=APP_ROOTS,
    )


def with_patch_path(patch: str, path: str) -> str:
    """Replace only the FILE section while preserving the two code sections."""
    normalized, count = _FILE_SECTION.subn(lambda match: f"{match[1]}\n{path}\n", patch, count=1)
    if count != 1:
        raise PatchPathError("Patch is missing its file section.")
    return normalized
