"""One proof-of-concept transmission, decoded and plotted."""

import importlib
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from leakyhammer import results, sim
from leakyhammer.defenses import Defense
from leakyhammer.metrics import parse_poc

EXPERIMENT = "poc"
"""Directory name under the results root."""

FIGURE_FILE = "figure.pdf"
"""Name of the figure written next to the log."""


def trial_name(defense: Defense, overrides: Mapping[str, Any]) -> str:
    """Returns the trial directory name, e.g. "dream_threshold62"."""
    return "_".join(
        [defense.name] + [f"{k}{v}" for k, v in sorted(overrides.items())]
    )


def plot(defense: Defense, log: Path, out: Path) -> None:
    """Draws the defense's POC figure from its log."""
    module = importlib.import_module(f"leakyhammer.plotting.poc_{defense.name}")
    module.plot(log, out)


def plot_trial(
    defense: Defense,
    batch: Path,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Path:
    """Draws the figure for a finished trial and returns its path.

    Not thread-safe (matplotlib's pyplot has global state): call from one
    thread at a time.
    """
    out_dir = batch / trial_name(defense, dict(overrides or {}))
    figure = out_dir / FIGURE_FILE
    plot(defense, out_dir / "sim.log", figure)
    return figure


def run_poc(
    defense: Defense,
    batch: Path,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Runs the defense's POC, stores its record, and returns the record.

    A crashed simulation or an undecodable log is recorded as failed (with
    its error) rather than raised. Safe to call from several threads.
    """
    overrides = dict(overrides or {})
    out_dir = batch / trial_name(defense, overrides)
    simulation = sim.poc(defense, out_dir, overrides)
    record: Dict[str, Any] = {
        "schema": results.SCHEMA_VERSION,
        "experiment": EXPERIMENT,
        "trial": out_dir.name,
        "status": "failed",
        "error": None,
        "params": {
            "defense": defense.name,
            "overrides": overrides,
            "options": defense.poc_options,
        },
        "sent_text": None,
        "decoded_text": None,
        "errors": None,
        "ber": None,
        "resyncs": None,
        "provenance": results.provenance(
            simulation.config_path, simulation.programs
        ),
    }
    try:
        simulation.run()
        decoded = parse_poc(simulation.log_path)
    except (RuntimeError, ValueError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    else:
        record.update(
            status="ok",
            sent_text=decoded.sent_text,
            decoded_text=decoded.decoded_text,
            errors=decoded.errors,
            ber=decoded.ber,
            resyncs=decoded.resyncs,
        )
    results.save_record(out_dir, record)
    return record
