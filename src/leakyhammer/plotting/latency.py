"""PRAC memory-request latency profile plot (paper figure 2)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

PathLike = Union[str, Path]


def _parse_latencies(file_name: PathLike) -> list[int]:
    """Extract per-request latencies from a gem5 log.

    Args:
        file_name: Path to the log containing a "Dump Begin" section.

    Returns:
        The third whitespace-separated token of each dump line, as ints.
    """
    parse = False
    latencies: list[int] = []
    with open(str(file_name), encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line == "Frontend":
                parse = False  # Stop parsing at the end of the dump
            if parse:
                tokens = line.split()
                if len(tokens) >= 3 and tokens[2].isdigit():
                    latencies.append(int(tokens[2]))
            if line == "Dump Begin":
                parse = True  # Start parsing at the start of the dump
    return latencies


def plot(log_path: PathLike, out_path: PathLike) -> None:
    """Plot the PRAC latency profile from a gem5 log.

    Args:
        log_path: Path to the gem5 log with the latency dump.
        out_path: Where to save the figure.
    """
    data = _parse_latencies(log_path)
    df = pd.DataFrame(data, columns=["Latency"]).reset_index()
    df.rename(columns={"index": "Time"}, inplace=True)

    fig, ax = plt.subplots(figsize=(8, 3))

    # Add background colors for y-axis ranges
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

    # add legend without latency
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

    # Adjust limits and ticks
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


if __name__ == "__main__":
    if len(sys.argv) > 2:
        plot(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python latency.py <input_file_name> <figure_name>")
        sys.exit(1)
