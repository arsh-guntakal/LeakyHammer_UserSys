"""One noise-sweep trial: send a message through a defense and decode it.

Also defines the sweep config and its trials, which "run.py" and "plot.py"
share. Example, one trial from the command line:

    python -m leakyhammer.experiments.noise_sweep.main --defense rfm \
        --pattern 0x55 --noise-rate 263
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from leakyhammer import results, sim
from leakyhammer.config import load_yaml_config, parse_overrides
from leakyhammer.defenses import Variant, get_defense, parse_variant
from leakyhammer.metrics import parse_log

EXPERIMENT = "noise_sweep"
"""Directory name under the results root."""

CONFIG_DIR = Path(__file__).parent / "configs"
"""Where named configs ("default", "quick", ...) live."""

_CONFIG_KEYS = {"variants", "patterns", "msg_bytes", "baseline", "noise"}


@dataclass(frozen=True)
class NoiseVariant(Variant):
    """A defense configuration in a sweep, with its noise rates.

    - noise_rates (tuple[int, ...] | None): overrides the defense's default
      noise rates when set.
    """

    noise_rates: Optional[Tuple[int, ...]] = None

    @property
    def rates(self: "NoiseVariant") -> Tuple[int, ...]:
        """Returns the noise rates swept for this variant."""
        if self.noise_rates is not None:
            return self.noise_rates
        return self.spec.noise_rates


@dataclass(frozen=True)
class SweepConfig:
    """A whole noise sweep; one config file describes one batch.

    - name (str): batch name (the config file's stem).
    - variants (tuple[NoiseVariant, ...]): configurations to measure.
    - patterns (tuple[str, ...]): data bytes to send, as hex strings.
    - msg_bytes (int): message length in bytes (8 bits each).
    - baseline (bool): include the no-noise measurement.
    - noise (bool): include the noise-rate measurements.
    """

    name: str
    variants: Tuple[NoiseVariant, ...]
    patterns: Tuple[str, ...]
    msg_bytes: int
    baseline: bool
    noise: bool


def _noise_variant(raw: object) -> NoiseVariant:
    """Converts one entry of "variants" (validated by "parse_variant")."""
    base = parse_variant(raw, {"noise_rates"})
    rates = raw.get("noise_rates")
    return NoiseVariant(
        base.defense,
        base.overrides,
        None if rates is None else tuple(int(r) for r in rates),
    )


def load_config(config: Union[str, Path]) -> SweepConfig:
    """Loads a sweep config by name (from "configs/") or by file path."""
    name, raw = load_yaml_config(config, CONFIG_DIR, _CONFIG_KEYS)
    if not raw.get("variants"):
        raise ValueError(f"{name}: 'variants' must list at least one entry")
    loaded = SweepConfig(
        name=name,
        variants=tuple(_noise_variant(v) for v in raw["variants"]),
        patterns=tuple(str(p) for p in raw.get("patterns", ["0x55"])),
        msg_bytes=int(raw.get("msg_bytes", 100)),
        baseline=bool(raw.get("baseline", True)),
        noise=bool(raw.get("noise", True)),
    )
    if not (loaded.baseline or loaded.noise):
        raise ValueError(f"{name}: need 'baseline' and/or 'noise' enabled")
    names = [v.name for v in loaded.variants]
    if len(set(names)) != len(names):
        raise ValueError(f"{name}: duplicate variants {names}")
    return loaded


@dataclass(frozen=True)
class Trial:
    """One simulation of the sweep.

    - variant (NoiseVariant): defense configuration under test.
    - pattern (str): data byte repeated through the message, as hex.
    - msg_bytes (int): message length in bytes.
    - noise_rate (int | None): background-noise activations per window, or
      None for the no-noise baseline.
    """

    variant: NoiseVariant
    pattern: str
    msg_bytes: int
    noise_rate: Optional[int]

    @property
    def id(self: "Trial") -> str:
        """Returns the trial's directory name."""
        return f"{self.variant.name}_p{self.pattern}_r{self.noise_rate or 0}"

    def simulation(self: "Trial", batch: Path) -> sim.Simulation:
        """Returns the gem5 simulation that runs this trial."""
        return sim.transmission(
            self.variant.spec,
            self.pattern,
            self.msg_bytes,
            batch / self.id,
            self.noise_rate,
            dict(self.variant.overrides),
        )


def trials(config: SweepConfig) -> List[Trial]:
    """Returns every trial of a sweep, baseline before noise."""
    found = []
    for variant in config.variants:
        rates: List[Optional[int]] = []
        if config.baseline:
            rates.append(None)
        if config.noise:
            rates.extend(variant.rates)
        for rate in rates:
            for pattern in config.patterns:
                found.append(Trial(variant, pattern, config.msg_bytes, rate))
    return found


def run_trial(
    trial: Trial,
    batch: Path,
    force: bool = False,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Runs a trial and stores its record; returns the record.

    A trial that already has a successful record is skipped unless "force".
    A crashed simulation is recorded as failed (with its error) rather than
    raised, so one failure does not lose the rest of a sweep.
    """
    trial_dir = batch / trial.id
    existing = results.load_record(trial_dir)
    if not force and existing is not None and existing["status"] == "ok":
        return existing

    simulation = trial.simulation(batch)
    error = None
    try:
        simulation.run(timeout=timeout)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    record = results.transmission_record(
        EXPERIMENT,
        trial.id,
        {
            "defense": trial.variant.defense,
            "overrides": dict(trial.variant.overrides),
            "pattern": trial.pattern,
            "msg_bytes": trial.msg_bytes,
            "noise_rate": trial.noise_rate or 0,
            "txn_period_ns": trial.variant.spec.txn_period_ns,
        },
        parse_log(simulation.log_path),
        results.provenance(simulation.config_path, simulation.programs),
        error,
    )
    results.save_record(trial_dir, record)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs a single trial from the command line; returns the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--defense", required=True)
    parser.add_argument(
        "--set",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="plugin parameter overrides",
    )
    parser.add_argument("--pattern", default="0x55", help="data byte, hex")
    parser.add_argument("--msg-bytes", type=int, default=100)
    parser.add_argument(
        "--noise-rate", type=int, default=0, help="0 means no noise"
    )
    parser.add_argument("--batch", default="single")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    spec = get_defense(args.defense)
    overrides = tuple(sorted(parse_overrides(args.set).items()))
    if overrides and spec.plugin_impl is None:
        raise ValueError(f"Defense '{spec.name}' takes no overrides")
    trial = Trial(
        NoiseVariant(spec.name, overrides),
        args.pattern,
        args.msg_bytes,
        args.noise_rate or None,
    )
    batch = results.batch_dir(EXPERIMENT, args.batch)
    record = run_trial(trial, batch, force=args.force)
    print(f"{trial.id}: {record['status']} -> {batch / trial.id}")
    if record["status"] != "ok":
        print(record["error"], file=sys.stderr)
        return 1
    print(
        f"errors {record['errors']}/{len(record['sent'])} "
        f"(BER {record['ber']:.4f}), {record['txn_time_ns']} ns"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
