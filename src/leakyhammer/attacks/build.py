"""Compiles the guest-side attack programs.

The senders, receivers and noise generator run *inside* the simulated machine
as static x86 binaries. They share "common/rowhammer-side.cc" and link only
gem5's "m5" library and headers; gem5 itself never links them. A defense's
programs live in "attacks/<defense>/" ("sender.cc", "receiver.cc",
"poc_sender.cc", "poc_receiver.cc") and compile to "<defense>_<role>".

Run "python -m leakyhammer.attacks.build --help" for the command line.
"""

import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from leakyhammer import paths
from leakyhammer.defenses import DEFENSES

COMMON_DIR = paths.ATTACK_SRC_DIR / "common"
"""Headers and the library source shared by every attack program."""

ROLES = ("sender", "receiver", "poc_sender", "poc_receiver")
"""Programs every defense provides, as "<role>.cc" in its directory."""

LEGACY_DIR = "./attack-scripts"
"""Directory the original artifact compiled its sources from."""


def legacy_name(defense: str, role: str) -> str:
    """Returns the original artifact's file name for a defense's program."""
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
    """

    name: str
    source: Path
    legacy_name: str
    flags: Tuple[str, ...] = BASE_FLAGS

    @property
    def output(self: "Target") -> Path:
        """Returns the path of the compiled program."""
        return paths.ATTACK_BIN_DIR / self.name


def targets() -> Dict[str, Target]:
    """Returns every compilable program, keyed by output name."""
    found: Dict[str, Target] = {}
    for defense in DEFENSES:
        for role in ROLES:
            name = f"{defense}_{role}"
            source = paths.ATTACK_SRC_DIR / defense / f"{role}.cc"
            if not source.exists():
                raise FileNotFoundError(
                    f"Defense '{defense}' is missing attack source {source}"
                )
            found[name] = Target(name, source, legacy_name(defense, role))
    found["mr_noise"] = Target(
        "mr_noise",
        paths.ATTACK_SRC_DIR / "noise" / "mr_noise.cc",
        "rowhammer-mr-noise.cc",
        (*BASE_FLAGS, "-Werror"),
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
        f"-ffile-prefix-map={COMMON_DIR}={LEGACY_DIR}",
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
        str(COMMON_DIR),
        "-I",
        str(paths.GEM5_INCLUDE_DIR),
        "-o",
        str(target.output),
        str(target.source),
        str(COMMON_DIR / "rowhammer-side.cc"),
        str(paths.M5_LIB),
    ]


def select(names: Sequence[str]) -> List[Target]:
    """Resolves command-line names to targets.

    A name is a program ("dream_sender"), a defense ("dream", all four of its
    programs), "noise", "latency", or "all". No names means "all".
    """
    available = targets()
    if not names or "all" in names:
        return list(available.values())
    chosen: Dict[str, Target] = {}
    for name in names:
        if name in available:
            chosen[name] = available[name]
        elif name in DEFENSES:
            for role in ROLES:
                chosen[f"{name}_{role}"] = available[f"{name}_{role}"]
        elif name in ("noise", "latency"):
            program = f"mr_{name}"
            chosen[program] = available[program]
        else:
            choices = [*sorted(available), *sorted(DEFENSES)]
            choices += ["noise", "latency", "all"]
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


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "targets", nargs="*", help="defense, program, noise, latency, or all"
    )
    parser.add_argument("-j", "--jobs", type=int, default=None)
    parser.add_argument(
        "--list", action="store_true", help="list programs and exit"
    )
    args = parser.parse_args(argv)
    if args.list:
        for name in targets():
            print(name)
        return
    for output in build(args.targets, args.jobs):
        print(f"built {output}")


if __name__ == "__main__":
    main()
