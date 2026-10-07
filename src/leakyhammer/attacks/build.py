"""Compiles the guest-side attack programs.

The senders, receivers and noise generator run *inside* the simulated machine
as static x86 binaries. They share "common/rowhammer-side.cc" and link only
gem5's "m5" library and headers; gem5 itself never links them. A defense's
programs live in "attacks/<defense>/" ("sender.cc", "receiver.cc",
"poc_sender.cc", "poc_receiver.cc") and compile to "<defense>_<role>".

The command line is "tools/compile-attacks".
"""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from leakyhammer import paths
from leakyhammer.defenses import ALL_ROLES, DEFENSES

COMMON_DIR = paths.ATTACK_SRC_DIR / "common"
"""Headers and the library source shared by every attack program."""

ROLES = ALL_ROLES
"""Programs a defense normally provides, as "<role>.cc" in its directory."""

LEGACY_DIR = "./attack-scripts"
"""Directory the original artifact compiled its sources from."""


def legacy_name(defense: str, role: str) -> str:
    """Returns the original artifact's file name for a defense's program.

    "defense" is the defense's name in the original artifact's file names
    ("Defense.legacy_stem" when it has one).
    """
    stem = {
        "sender": f"rowhammer-{defense}-sender",
        "receiver": f"rowhammer-{defense}-receiver",
        "poc_sender": f"{defense}-poc-sender",
        "poc_receiver": f"{defense}-poc-receiver",
    }[role]
    return f"{stem}.cc"


BASE_FLAGS = ("-static", "-g", "-Wall", "-O3")
"""Compiler flags used for every program."""


@dataclass(frozen=True)
class Target:
    """One attack program to compile.

    - name (str): output file name in "ATTACK_BIN_DIR".
    - source (Path): the program's own source; "rowhammer-side.cc" is added.
    - legacy_name (str): the source's file name in the original artifact,
      which is embedded in the binary (see "compile_command").
    - flags (tuple[str, ...]): compiler flags.
    - common_dir (Path): where "rowhammer-side.cc" and its headers are; a
      legacy defense carries its own copy.
    """

    name: str
    source: Path
    legacy_name: str
    flags: Tuple[str, ...] = BASE_FLAGS
    common_dir: Path = COMMON_DIR

    @property
    def output(self: "Target") -> Path:
        """Returns the path of the compiled program."""
        return paths.ATTACK_BIN_DIR / self.name


def targets() -> Dict[str, Target]:
    """Returns every compilable program, keyed by output name."""
    found: Dict[str, Target] = {}
    for defense in DEFENSES.values():
        own_library = (defense.source_dir / "rowhammer-side.cc").exists()
        for role in defense.roles:
            name = f"{defense.name}_{role}"
            source = defense.source_dir / f"{role}.cc"
            if not source.exists():
                raise FileNotFoundError(
                    f"Defense '{defense.name}' is missing attack source "
                    f"{source}"
                )
            found[name] = Target(
                name,
                source,
                legacy_name(defense.legacy_stem or defense.name, role),
                common_dir=defense.source_dir if own_library else COMMON_DIR,
            )
    found["mr_noise"] = Target(
        "mr_noise",
        paths.ATTACK_SRC_DIR / "noise" / "mr_noise.cc",
        "rowhammer-mr-noise.cc",
        (*BASE_FLAGS, "-Werror"),
    )
    found["latency_histogram"] = Target(
        "latency_histogram",
        paths.ATTACK_SRC_DIR / "diagnostics" / "latency_histogram.cc",
        "latency_histogram.cc",
    )
    found["mr_latency"] = Target(
        "mr_latency",
        paths.ATTACK_SRC_DIR / "latency" / "mr_latency.cc",
        "rowhammer-mr-latency.cc",
    )
    return found


def _path_maps(target: Target) -> List[str]:
    """Returns the "-ffile-prefix-map" flags that fix embedded source paths.

    The compiler embeds source paths (for "assert") in the binary's read-only
    data. Their lengths shift every constant after them, and with it how data
    falls on cache lines, which measurably changes the measurements (the RFM
    baseline's 0x55 run gave 109 bit errors instead of 106). So the paths are
    mapped to exactly what the original artifact embedded, making each program
    byte-identical in its loaded sections to the original build, regardless of
    where this repository is checked out. Later maps win, so the specific ones
    come last.
    """
    return [
        f"-ffile-prefix-map={paths.REPO_ROOT}=.",
        f"-ffile-prefix-map={target.common_dir}={LEGACY_DIR}",
        f"-ffile-prefix-map={target.source}={LEGACY_DIR}/{target.legacy_name}",
    ]


def compile_command(target: Target, cxx: Optional[str] = None) -> List[str]:
    """Returns the compiler invocation that builds "target".

    The compiler is the system "g++" unless "LEAKYHAMMER_CXX" (or "cxx") says
    otherwise. It deliberately ignores "CXX": the container sets that to
    g++-10 for building gem5, but the original artifact built these programs
    with the default g++ (9.4), and g++-10 produces a differently laid-out
    binary. Guest memory layout changes the measurements (BERs and POC
    outcomes shift), so changing the compiler changes the results.
    """
    return [
        cxx or os.environ.get("LEAKYHAMMER_CXX", "g++"),
        *target.flags,
        *_path_maps(target),
        "-I",
        str(target.common_dir),
        "-I",
        str(paths.GEM5_INCLUDE_DIR),
        "-o",
        str(target.output),
        str(target.source),
        str(target.common_dir / "rowhammer-side.cc"),
        str(paths.M5_LIB),
    ]


def select(names: Sequence[str]) -> List[Target]:
    """Resolves command-line names to targets.

    A name is a program ("dream_sender"), a defense ("dream", all of its
    programs), "noise", "latency", "diagnostics", or "all". No names means
    "all".
    """
    available = targets()
    if not names or "all" in names:
        return list(available.values())
    chosen: Dict[str, Target] = {}
    for name in names:
        if name in available:
            chosen[name] = available[name]
        elif name in DEFENSES:
            for role in DEFENSES[name].roles:
                chosen[f"{name}_{role}"] = available[f"{name}_{role}"]
        elif name in ("noise", "latency"):
            program = f"mr_{name}"
            chosen[program] = available[program]
        elif name == "diagnostics":
            chosen["latency_histogram"] = available["latency_histogram"]
        else:
            choices = [*sorted(available), *sorted(DEFENSES)]
            choices += ["noise", "latency", "diagnostics", "all"]
            raise ValueError(f"Unknown target '{name}'; choose from {choices}")
    return list(chosen.values())


def build(names: Sequence[str] = (), jobs: Optional[int] = None) -> List[Path]:
    """Compiles the selected programs and returns their paths.

    Raises "FileNotFoundError" if gem5's m5 library has not been built yet
    ("tools/build --gem5" builds it).
    """
    if not paths.M5_LIB.exists():
        raise FileNotFoundError(
            f"{paths.M5_LIB} not found; build gem5 first (tools/build)"
        )
    selected = select(names)
    paths.ATTACK_BIN_DIR.mkdir(parents=True, exist_ok=True)

    def compile_one(target: Target) -> Path:
        subprocess.run(compile_command(target), check=True)
        return target.output

    with ThreadPoolExecutor(max_workers=jobs or os.cpu_count() or 1) as pool:
        return list(pool.map(compile_one, selected))
