"""Figure of a finished latency profile, one per defense in a config.

Example:
    python -m leakyhammer.experiments.latency_profile.plot --config default
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Union

import matplotlib

# Headless-safe; must be selected before pyplot is first imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from leakyhammer import results
from leakyhammer.experiments.latency_profile.main import (
    EXPERIMENT,
    load_config,
)

FIGURE_FILE = "figure.pdf"
"""Name of the figure written next to each trial's log."""


def parse_latencies(log_path: Union[str, Path]) -> List[int]:
    """Extracts per-request latencies from a simulation log.

    The log holds a "Dump Begin" section; the third whitespace-separated
    token of each line in it is a latency in nanoseconds.
    """
    parse = False
    latencies: List[int] = []
    with open(str(log_path), encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line == "Frontend":
                parse = False  # The dump ends where the frontend config starts.
            if parse:
                tokens = line.split()
                if len(tokens) >= 3 and tokens[2].isdigit():
                    latencies.append(int(tokens[2]))
            if line == "Dump Begin":
                parse = True
    return latencies


def plot_latency(
    log_path: Union[str, Path], out_path: Union[str, Path]
) -> None:
    """Plots memory-request latency, colored by what causes each band."""
    data = parse_latencies(log_path)
    df = pd.DataFrame(data, columns=["Latency"]).reset_index()
    df.rename(columns={"index": "Time"}, inplace=True)

    fig, ax = plt.subplots(figsize=(8, 3))

    ax.axhspan(1250, 3500, color="#71b9de", alpha=0.3, label="PRAC Back-off")
    ax.axhspan(250, 1250, color="#ffd766", alpha=0.3, label="Periodic Refresh")
    ax.axhspan(80, 250, color="#83d67a", alpha=0.3, label="Row Buffer Conflict")

    sns.lineplot(
        data=df,
        x="Time",
        y="Latency",
        ax=ax,
        color="black",
        label="Latency",
        linewidth=1.5,
    )

    ax.set_xlabel("Memory Requests", fontsize=14)
    ax.set_ylabel("Memory Request\nLatency (ns)", fontsize=14)
    ax.grid(axis="y", linestyle="--", alpha=0.7)

    # The legend names the bands, not the latency line itself.
    legend_handles, legend_labels = ax.get_legend_handles_labels()
    legend_labels = [label for label in legend_labels if label != "Latency"]
    ax.legend(
        legend_handles,
        legend_labels,
        loc="upper center",
        fontsize=12,
        ncol=len(legend_labels),
        framealpha=1,
        bbox_to_anchor=(0.5, 1.26),
        fancybox=False,
        edgecolor="black",
        handlelength=1,
        handleheight=1,
        handletextpad=0.5,
    )

    plt.ylim(0, 1750)
    plt.yscale("linear")
    plt.xlim(1024, 1024 + 512)
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.yticks(np.arange(0, 1751, 500))

    plt.text(
        1400,
        1375,
        "<------- 255 memory requests ------->",
        fontsize=12,
        color="red",
        ha="center",
        va="center",
        style="italic",
    )

    plt.tight_layout()
    plt.savefig(str(out_path), bbox_inches="tight", dpi=300)
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
    status = 0
    for variant in config.variants:
        trial_dir = batch / variant.name
        record = results.load_record(trial_dir)
        if record is None or record["status"] != "ok":
            print(f"{variant.name}: no successful run to plot")
            status = 1
            continue
        out = trial_dir / FIGURE_FILE
        plot_latency(trial_dir / "sim.log", out)
        print(f"wrote {out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
