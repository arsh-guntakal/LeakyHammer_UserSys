"""Figure and table of a finished mitigation-trace batch.

Plots mitigations against one-bits per pattern, the correctness evidence: a
defense that mitigates proportionally to genuine hammering, and not at all
when idle, is doing what it is specified to do. Example:

    python -m leakyhammer.experiments.mitigation_trace.plot --config default
"""

import argparse
import sys
from typing import Any, Dict, List, Optional, Sequence

import matplotlib

# Headless-safe; must be selected before pyplot is first imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from leakyhammer import results
from leakyhammer.experiments.mitigation_trace.main import (
    EXPERIMENT,
    load_config,
    trial_name,
)

FIGURE_FILE = "figure.pdf"
"""Name of the figure written in the batch directory."""


def summarize(records: List[Dict[str, Any]]) -> None:
    """Prints mitigations against hammering windows for every ok trial."""
    print(f"{'pattern':>8} {'hammering windows':>18} {'mitigations':>12}")
    for record in records:
        print(
            f"{record['params']['pattern']:>8} "
            f"{record['hammering_windows']:>18} {record['mitigations']:>12}"
        )


def plot_mitigations(records: List[Dict[str, Any]], out_path: str) -> None:
    """Draws mitigations against hammering windows, one bar per pattern."""
    patterns = [r["params"]["pattern"] for r in records]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    xs = range(len(records))
    ax.bar(xs, [r["mitigations"] for r in records], color="#4c72b0")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(
        [
            f"{p}\n({r['hammering_windows']} hammering windows)"
            for p, r in zip(patterns, records)
        ],
        fontsize=8,
    )
    ax.set_ylabel("DRFMab mitigations issued")
    ax.set_xlabel("data pattern")
    ax.set_title("DREAM-C mitigates in proportion to how much it is hammered")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config", required=True, help="config name or YAML path"
    )
    parser.add_argument("--batch", default=None)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    batch = results.batch_dir(EXPERIMENT, args.batch or config.name)
    found = [
        results.load_record(batch / trial_name(config.threshold, p))
        for p in config.patterns
    ]
    ok = [r for r in found if r and r["status"] == "ok"]
    for record, pattern in zip(found, config.patterns):
        if record is None or record["status"] != "ok":
            error = record["error"] if record else "not run"
            print(f"{pattern}: no result ({error})")
    if not ok:
        print("nothing to plot", file=sys.stderr)
        return 1
    summarize(ok)
    plot_mitigations(ok, str(batch / FIGURE_FILE))
    print(f"wrote {batch / FIGURE_FILE}")
    return 0 if len(ok) == len(found) else 1


if __name__ == "__main__":
    sys.exit(main())
