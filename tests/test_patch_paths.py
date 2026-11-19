from pathlib import Path

import pytest

from agents.patch_paths import (
    PatchPathError, WORKSPACE_MOUNTS, canonical_app_path, canonical_patch_path, with_patch_path,
)


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    (root / "app").mkdir(parents=True)
    (root / "app/module.py").write_text("def main():\n    return True\n")
    (root / "module.py").write_text("pass\n")
    return root


@pytest.mark.parametrize("submitted", ("module.py", "app/module.py", "/app/module.py", "/app/app/module.py"))
def test_application_aliases_map_before_allowlisting(checkout, submitted):
    assert canonical_app_path(checkout, submitted) == "app/module.py"


def test_workspace_mount_is_repository_relative_even_with_duplicate_basenames(checkout):
    assert canonical_patch_path(
        checkout, "/workspace/module.py", mounts=WORKSPACE_MOUNTS, unique_basename=True,
    ) == "module.py"
    assert canonical_patch_path(
        checkout, "/workspace/app/module.py", mounts=WORKSPACE_MOUNTS,
    ) == "app/module.py"
    with pytest.raises(PatchPathError, match="unique"):
        canonical_patch_path(checkout, "module.py", unique_basename=True)


@pytest.mark.parametrize("submitted", (
    "../module.py", "app/../module.py", "/app/../module.py",
    "/etc/module.py", "/workspace-other/app/module.py", "C:\\module.py",
))
def test_traversal_and_unknown_host_absolute_paths_fail(checkout, submitted):
    with pytest.raises(PatchPathError):
        canonical_app_path(checkout, submitted)


def test_symlinks_resolve_before_the_allowlist(checkout):
    outside = checkout.parent / "outside.py"
    outside.write_text("secret = 1\n")
    (checkout / "app/escape.py").symlink_to(outside)
    (checkout / "app/internal.py").symlink_to(Path("module.py"))
    (checkout / "app/out-of-scope.py").symlink_to(Path("../module.py"))
    (checkout / "app/foreign").symlink_to(outside.parent, target_is_directory=True)
    with pytest.raises(PatchPathError, match="inside the checkout"):
        canonical_app_path(checkout, "/app/escape.py")
    with pytest.raises(PatchPathError, match="inside the checkout"):
        canonical_app_path(checkout, "/app/foreign/outside.py")
    with pytest.raises(PatchPathError, match="allowlist"):
        canonical_app_path(checkout, "/app/out-of-scope.py")
    assert canonical_app_path(checkout, "/app/internal.py") == "app/module.py"


def test_protected_files_are_rejected_even_via_an_allowed_alias(checkout):
    protected = checkout / "app/tests"
    protected.mkdir()
    (protected / "contract.py").touch()
    (checkout / "app/allowed.py").symlink_to(Path("tests/contract.py"))
    with pytest.raises(PatchPathError, match="allowlist"):
        canonical_app_path(checkout, "/app/allowed.py")


def test_rewriting_path_keeps_code_section_whitespace():
    body = "===ORIGINAL===\n    old()\n===FIXED===\n    new()\n"
    assert with_patch_path("===FILE===\n/app/module.py\n" + body, "app/module.py") == (
        "===FILE===\napp/module.py\n" + body
    )
