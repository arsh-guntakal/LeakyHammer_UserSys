"""One noise-sweep trial: send a message through a defense and decode it."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from leakyhammer import results, sim
from leakyhammer.experiments.noise_sweep.config import SweepConfig, Variant
from leakyhammer.metrics import parse_log

EXPERIMENT = "noise_sweep"
"""Directory name under the results root."""


@dataclass(frozen=True)
class Trial:
    """One simulation of the sweep.

    - variant (Variant): defense configuration under test.
    - pattern (str): data byte repeated through the message, as hex.
    - msg_bytes (int): message length in bytes.
    - noise_rate (int | None): background-noise activations per window, or
      None for the no-noise baseline.
    """

    variant: Variant
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
