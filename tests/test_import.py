"""Ensures every module imports without side effects."""

import importlib
import pkgutil

import pytest

import leakyhammer


@pytest.mark.unit
def test_every_module_imports() -> None:
    """Importing any module must not run simulations, argparse, or I/O.

    Regression guard for the original script-style code, where importing
    "setup_test" parsed arguments and deleted "run_scripts".
    """
    names = [
        m.name
        for m in pkgutil.walk_packages(leakyhammer.__path__, "leakyhammer.")
    ]
    assert len(names) > 20
    for name in names:
        importlib.import_module(name)
