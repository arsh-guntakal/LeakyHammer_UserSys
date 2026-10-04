"""The repository is ruff-clean (also enforced in CI)."""

import subprocess
import sys

import pytest

from leakyhammer import paths


@pytest.mark.unit
@pytest.mark.parametrize("args", [["check"], ["format", "--check"]])
def test_ruff_clean(args: list) -> None:
    """ "ruff check" and "ruff format --check" report nothing to fix."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        cwd=paths.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
