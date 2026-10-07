"""Table and figure of a finished latency-histogram batch.

For each variant, compares the probes' latency distribution in windows where
the sender sent 1 with windows where it sent 0. Example:

    python -m leakyhammer.experiments.latency_histogram.plot --config default
"""

import argparse
import sys
from typing import Any, Dict, List, Optional, Sequence

import matplotlib

# Headless-safe; must be selected before pyplot is first imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from leakyhammer import results
from leakyhammer.experiments.latency_histogram.main import (
    EXPERIMENT,
    HistVariant,
    load_config,
)

FIGURE_FILE = "figure.pdf"
"""Name of the figure written in the batch directory."""


def bin_labels(edges_ns: List[int]) -> List[str]:
    """Returns one label per latency bin, e.g. "<100", "100-150", ">3000"."""
    labels = [f"<{edges_ns[0]}"]
    labels += [f"{lo}-{hi}" for lo, hi in zip(edges_ns, edges_ns[1:])]
    labels.append(f">{edges_ns[-1]}")
    return labels


def tail_difference(record: Dict[str, Any], above_ns: int) -> float:
    """Returns the extra slow probes per window when the sender sends a 1.

    Counts probes in bins whose lower edge is at least "above_ns", as the mean
    over windows of a 1 minus the mean over windows of a 0. Near zero means a
    receiver sees no difference, whatever the sender did.
    """
    edges = record["edges_ns"]
    first = next((i + 1 for i, e in enumerate(edges) if e >= above_ns), None)
    if first is None:
        raise ValueError(f"No latency bin starts at or above {above_ns} ns")
    ones = sum(record["mean_probes"]["1"][first:])
    zeros = sum(record["mean_probes"]["0"][first:])
    return ones - zeros


def plot_histograms(
    records: Dict[str, Dict[str, Any]],
    labels: Dict[str, str],
    out_path: str,
) -> None:
    """Draws one panel per trial: mean probes per bin, sent 1 against sent 0."""
    fig, axes = plt.subplots(
        len(records), 1, figsize=(8, 2.2 * len(records)), squeeze=False
    )
    for ax, (name, record) in zip(axes[:, 0], records.items()):
        names = bin_labels(record["edges_ns"])
        xs = range(len(names))
        ax.bar(
            [x - 0.2 for x in xs],
            record["mean_probes"]["0"],
            width=0.4,
            label="sent 0",
        )
        ax.bar(
            [x + 0.2 for x in xs],
            record["mean_probes"]["1"],
            width=0.4,
            label="sent 1",
        )
        ax.set_yscale("log")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(names, fontsize=8)
        ax.set_ylabel("probes / window", fontsize=8)
        ax.set_title(labels[name], fontsize=9, loc="left")
        ax.legend(fontsize=7)
    axes[-1, 0].set_xlabel("probe latency (ns)")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def summarize(
    variants: Sequence[HistVariant], batch_records: Dict[str, Any]
) -> None:
    """Prints, per variant, the extra slow probes in windows of a 1."""
    for variant in variants:
        record = batch_records.get(variant.name)
        if record is None or record["status"] != "ok":
            error = record["error"] if record else "not run"
            print(f"{variant.label}: no result ({error})")
            continue
        diff = tail_difference(record, 250)
        print(
            f"{variant.label}: slow probes (>=250 ns) per window, "
            f"sent 1 minus sent 0: {diff:+.2f}"
        )


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
    found = {
        v.name: results.load_record(batch / v.name) for v in config.variants
    }
    summarize(config.variants, {k: r for k, r in found.items() if r})
    ok = {
        v.name: found[v.name]
        for v in config.variants
        if found[v.name] and found[v.name]["status"] == "ok"
    }
    if not ok:
        print("nothing to plot", file=sys.stderr)
        return 1
    plot_histograms(
        ok,
        {v.name: v.label for v in config.variants},
        str(batch / FIGURE_FILE),
    )
    print(f"wrote {batch / FIGURE_FILE}")
    return 0 if len(ok) == len(config.variants) else 1


if __name__ == "__main__":
    sys.exit(main())
