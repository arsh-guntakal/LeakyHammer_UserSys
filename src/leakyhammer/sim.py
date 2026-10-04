"""Builds and runs gem5 simulations of the attack.

A "Simulation" is a fully specified gem5 command plus the directory it writes
to. Each simulation is self-contained ("<out_dir>/sim.log" holds its output
and "<out_dir>/m5out/" gem5's own files), so any number can run in parallel.
"""

import copy
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from leakyhammer import paths
from leakyhammer.defenses import Defense

MSG_PROCESS_COUNT = 2
"""CPUs for a transmission without noise: the sender and the receiver."""

NOISE_PROCESS_COUNT = 3
"""CPUs for a transmission with noise: sender, receiver, noise generator."""

NOISE_ROW_IDX = 32
"""Row index argument the noise generator is started with."""

# gem5 and cache configuration shared by every simulation, unchanged from the
# LeakyHammer artifact except for the memory size.
_COMMON_FLAGS = (
    "--cpu-type=O3CPU",
    "--sys-clock=1GHz",
    "--cpu-clock=3GHz",
    "--mem-type=Ramulator2",
    # 32 GB because DREAM's sender synthesizes physical addresses up to
    # ~16 GB (two-bank gang collision under DDR5_16Gb_x8). The size only
    # bounds the address space and does not change DRAM timing, so PRAC and
    # RFM results are unaffected.
    "--mem-size=32GB",
    "--caches",
    "--l2cache",
    "--num-l2caches=1",
    "--l1d_size=32kB",
    "--l1i_size=32kB",
    "--l2_size=4MB",
    "--l1d_assoc=8",
    "--l1i_assoc=8",
    "--l2_assoc=16",
    "--cacheline_size=64",
)

GUEST_BIN_DIR_ENV = "LEAKYHAMMER_GUEST_BIN_DIR"
"""If set, guest programs are started by absolute path under this directory
instead of "./<name>" from the binaries directory. See "guest_program"."""

# Environment variables that can redirect gem5's embedded Python away from the
# system interpreter it was linked against (e.g. when launched from a uv env).
_SCRUBBED_ENV = ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH")


@dataclass
class Simulation:
    """One gem5 run.

    - command (list[str]): the full argument vector.
    - out_dir (Path): directory this run owns; created by "run".
    - config_path (Path): the Ramulator2 config the run uses (the checked-in
      one, or a per-trial copy with overrides applied).
    - programs (list[Path]): the guest programs the run executes.
    - cwd (Path | None): directory to run gem5 from; None means the current
      one. Set when guest programs are named relative to it.
    """

    command: List[str]
    out_dir: Path
    config_path: Path
    programs: List[Path]
    cwd: Optional[Path] = None

    @property
    def log_path(self: "Simulation") -> Path:
        """Returns the file the simulation's output is written to."""
        return self.out_dir / "sim.log"

    def shell_command(self: "Simulation") -> str:
        """Returns the command as a single shell line, redirecting output.

        Useful for handing a run to another scheduler (xargs, Slurm).
        """
        log = shlex.quote(str(self.log_path))
        line = f"{shlex.join(self.command)} > {log} 2>&1"
        if self.cwd is not None:
            line = f"cd {shlex.quote(str(self.cwd))} && {line}"
        return line

    def run(self: "Simulation", timeout: Optional[float] = None) -> Path:
        """Runs the simulation to completion and returns its log path.

        Raises "RuntimeError" if gem5 exits non-zero (the log is kept).
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED_ENV}
        with open(self.log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run(
                self.command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=self.cwd,
                timeout=timeout,
                check=False,
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"gem5 exited with status {proc.returncode}; "
                f"see {self.log_path}"
            )
        return self.log_path


def guest_program(program: Path) -> str:
    """Returns the string gem5 starts a guest program with (its "argv[0]").

    By default "./<name>", run from the binaries directory. The string is
    copied onto the simulated process's stack, and measured results depend on
    its length (PRAC's baseline timing and RFM's 0xFF bit errors shift when it
    gets one byte longer), so it must not depend on where the repository is
    checked out. "LEAKYHAMMER_GUEST_BIN_DIR" instead selects an absolute
    directory, to reproduce a measurement made with a specific path.
    """
    override = os.environ.get(GUEST_BIN_DIR_ENV)
    if override:
        return f"{override.rstrip('/')}/{program.name}"
    return f"./{program.name}"


def _cwd() -> Optional[Path]:
    """Returns the directory gem5 must run from for "guest_program" names."""
    return None if os.environ.get(GUEST_BIN_DIR_ENV) else paths.ATTACK_BIN_DIR


def _gem5_command(
    out_dir: Path,
    num_cpu: int,
    config_path: Path,
    programs: List[Path],
    options: List[str],
) -> List[str]:
    """Returns the gem5 argument vector for a set of guest programs."""
    return [
        str(paths.GEM5_BIN),
        f"--outdir={out_dir / 'm5out'}",
        str(paths.GEM5_SE_SCRIPT),
        f"--num-cpu={num_cpu}",
        *_COMMON_FLAGS,
        f"--ramulator-config={config_path}",
        f"--cmd={';'.join(guest_program(p) for p in programs)}",
        f"--options={';'.join(options)}",
    ]


def effective_config(
    defense: Defense,
    out_dir: Path,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Path:
    """Returns the Ramulator2 config to use, applying plugin overrides.

    With no overrides this is the defense's checked-in config. Otherwise a
    modified copy is written to "<out_dir>/ramulator.yaml", so a sweep over a
    plugin parameter (e.g. DREAM's "threshold") never edits tracked files and
    each trial records exactly the config it ran with.
    """
    if not overrides:
        return defense.config_path
    if defense.plugin_impl is None:
        raise ValueError(f"Defense '{defense.name}' has no tunable plugin")
    config = yaml.safe_load(defense.config_path.read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    plugins: List[Dict[str, Any]] = config["MemorySystem"]["BHDRAMController"][
        "plugins"
    ]
    matches = [
        p["ControllerPlugin"]
        for p in plugins
        if p.get("ControllerPlugin", {}).get("impl") == defense.plugin_impl
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one {defense.plugin_impl} plugin in "
            f"{defense.config_path}, found {len(matches)}"
        )
    unknown = sorted(set(overrides) - set(matches[0]))
    if unknown:
        raise ValueError(
            f"{defense.plugin_impl} has no parameter(s) {unknown}; "
            f"known: {sorted(matches[0])}"
        )
    matches[0].update(overrides)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ramulator.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def transmission(
    defense: Defense,
    pattern: str,
    msg_bytes: int,
    out_dir: Path,
    noise_rate: Optional[int] = None,
    config_overrides: Optional[Mapping[str, Any]] = None,
) -> Simulation:
    """Returns a simulation sending "msg_bytes" of a repeated bit pattern.

    - pattern: byte to repeat, as hex (e.g. "0x55").
    - noise_rate: if given, a third process generates background memory
      traffic at this many activations per window; None means no noise.
    """
    out_dir = Path(out_dir)
    config = effective_config(defense, out_dir, config_overrides)
    window = defense.txn_period_ns
    args = f"{window} {msg_bytes} {pattern}"
    programs: List[Path] = [defense.sender, defense.receiver]
    options = [args, args]
    num_cpu = MSG_PROCESS_COUNT
    if noise_rate is not None:
        # The generator runs for 1.5x the time the message takes to send. The
        # period is written as a float ("24000000.0") because the original
        # artifact did: the program only reads the integer part, but the
        # string is copied onto the simulated stack and its length changes
        # the noise runs' results.
        attack_period = window * msg_bytes * 8 * 1.5
        programs.append(paths.ATTACK_BIN_DIR / "mr_noise")
        options.append(f"{attack_period:.1f} {NOISE_ROW_IDX} {noise_rate}")
        num_cpu = NOISE_PROCESS_COUNT
    return Simulation(
        _gem5_command(out_dir, num_cpu, config, programs, options),
        out_dir,
        config,
        programs,
        _cwd(),
    )


def poc(
    defense: Defense,
    out_dir: Path,
    config_overrides: Optional[Mapping[str, Any]] = None,
) -> Simulation:
    """Returns the proof-of-concept simulation (a short text message)."""
    out_dir = Path(out_dir)
    config = effective_config(defense, out_dir, config_overrides)
    programs = [defense.poc_sender, defense.poc_receiver]
    options = [defense.poc_options, defense.poc_options]
    return Simulation(
        _gem5_command(out_dir, MSG_PROCESS_COUNT, config, programs, options),
        out_dir,
        config,
        programs,
        _cwd(),
    )


def latency_profile(defense: Defense, out_dir: Path) -> Simulation:
    """Returns the single-process memory-latency profile simulation."""
    out_dir = Path(out_dir)
    programs = [paths.ATTACK_BIN_DIR / "mr_latency"]
    return Simulation(
        _gem5_command(out_dir, 1, defense.config_path, programs, ["1600 2"]),
        out_dir,
        defense.config_path,
        programs,
        _cwd(),
    )
