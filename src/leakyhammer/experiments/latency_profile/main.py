"""Runs the latency-profile simulation and plots it.

Example:
    python -m leakyhammer.experiments.latency_profile.main
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from leakyhammer import results, sim
from leakyhammer.defenses import get_defense
from leakyhammer.plotting import latency

EXPERIMENT = "latency_profile"
"""Directory name under the results root."""


def run(batch: Path, figure: bool = True) -> Path:
    """Runs the profile under PRAC; returns the figure (or log) path."""
    simulation = sim.latency_profile(get_defense("prac"), batch)
    log = simulation.run()
    if not figure:
        return log
    out = batch / "figure.pdf"
    latency.plot(log, out)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--batch", default="default")
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args(argv)
    out = run(results.batch_dir(EXPERIMENT, args.batch), not args.no_figure)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
