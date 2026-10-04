"""Shared fixtures; fails collection for tests without a marker."""

from pathlib import Path
from typing import List

import pytest

DATA = Path(__file__).parent / "data"

MARKERS = {"unit", "integration", "slow", "regression", "experiment"}


def pytest_collection_modifyitems(items: List[pytest.Item]) -> None:
    """Requires every test to carry at least one of our markers."""
    unmarked = [
        item.nodeid
        for item in items
        if not MARKERS & {m.name for m in item.iter_markers()}
    ]
    if unmarked:
        raise pytest.UsageError(
            "Tests need a marker (unit/integration/...): " + ", ".join(unmarked)
        )


@pytest.fixture
def data() -> Path:
    """Returns the directory of small log/CSV fixtures."""
    return DATA


@pytest.fixture
def results_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points the results store at a temporary directory."""
    from leakyhammer import paths

    monkeypatch.setattr(paths, "RESULTS_DIR", tmp_path / "results")
    return tmp_path / "results"
