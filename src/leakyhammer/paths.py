"""Locations of the simulator, compiled attack binaries, and results.

Everything resolves from the repository root. The root is found relative to
this file (the package is installed in editable mode), and can be overridden
with the "LEAKYHAMMER_ROOT" environment variable. Results go to
"LEAKYHAMMER_RESULTS" when set, which is useful for putting large outputs on
another disk.
"""

import os
from pathlib import Path


def _repo_root() -> Path:
    """Returns the repository root."""
    override = os.environ.get("LEAKYHAMMER_ROOT")
    if override:
        return Path(override).resolve()
    # src/leakyhammer/paths.py -> repository root.
    return Path(__file__).resolve().parents[2]


REPO_ROOT = _repo_root()
"""Repository root."""

GEM5_DIR = REPO_ROOT / "gem5"
"""The vendored gem5 (+ Ramulator2) tree. See "gem5/PATCHES.md"."""

GEM5_BIN = GEM5_DIR / "build" / "X86" / "gem5.opt"
"""The simulator binary produced by "tools/build"."""

GEM5_SE_SCRIPT = GEM5_DIR / "configs" / "deprecated" / "example" / "se.py"
"""gem5's syscall-emulation config script."""

GEM5_INCLUDE_DIR = GEM5_DIR / "include"
"""gem5 headers ("gem5/m5ops.h") the guest attack programs include."""

M5_LIB = GEM5_DIR / "util" / "m5" / "build" / "x86" / "out" / "libm5.a"
"""gem5's guest-side m5 library the attack programs link against."""

RAMULATOR_CONFIG_DIR = GEM5_DIR / "configs" / "rhsc" / "ramulator"
"""Ramulator2 YAML configuration, one file per defense."""

ATTACK_SRC_DIR = REPO_ROOT / "src" / "leakyhammer" / "attacks"
"""Guest-side C++ sources (senders, receivers, noise generator)."""

BUILD_DIR = REPO_ROOT / "build"
"""Generated build outputs that are not gem5's own."""

ATTACK_BIN_DIR = BUILD_DIR / "attack-binaries"
"""Compiled attack programs, run inside the simulated machine."""

RESULTS_DIR = Path(os.environ.get("LEAKYHAMMER_RESULTS", REPO_ROOT / "results"))
"""Root of all experiment results: "<experiment>/<batch>/<trial>/"."""
