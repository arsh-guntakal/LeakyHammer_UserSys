"""PRAC channel capacity versus noise intensity plot (paper figure 4)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

PathLike = Union[str, Path]


def plot(
    csv_path: PathLike, out_path: PathLike, msg_bytes: int
) -> dict[str, float]:
    """Plot PRAC error probability and capacity versus noise intensity.

    Prints the same summary lines as the original script.

    Args:
        csv_path: Path to the noise BER CSV (columns include rate, errors,
            time, sent, received).
        out_path: Where to save the figure.
        msg_bytes: Message length in bytes used to compute bit rates.

    Returns:
        Dict with keys "capacity_88pct" (channel capacity near 88%
        intensity, Kbps) and "capacity_lowest" (near 1% intensity, Kbps).
    """
    num_bits = msg_bytes * 8

    data = pd.read_csv(
        str(csv_path), index_col=False, dtype={"sent": str, "received": str}
    )
    plot_data = data[(data["rate"] >= 0) & (data["errors"] >= 0)].sort_values(
        by="rate"
    )
    average_errors = plot_data.groupby("rate")["errors"].mean().reset_index()
    average_time = plot_data.groupby("rate")["time"].mean().reset_index()

    df = average_errors.copy()
    df = pd.merge(df, average_time, on="rate", how="inner")
    df["rate"] = df["rate"].astype(int)
    df = df[df["rate"] > 175]

    df["rate"] = df["rate"] - 175

    # make errorprob values that are 0 to 0.0001
    df.loc[df["errors"] == 0, "errors"] = 0.0001

    df["intensity"] = (
        100
        - (df["rate"].astype(float) - df["rate"].min())
        / (df["rate"].max() - df["rate"].min())
        * 100
    )
    df["errorprob"] = df["errors"] / num_bits

    # time column is in nanoseconds, so divide by 1e9 to get seconds
    df["time_s"] = df["time"] / 1e9

    df["rawbitrate"] = num_bits / df["time_s"] / 1024

    df["entropy"] = (-1 * df["errorprob"] * np.log2(df["errorprob"])) - (
        (1 - df["errorprob"]) * np.log2(1 - df["errorprob"])
    )
    df["capacity"] = (1 - df["entropy"]) * df["rawbitrate"]

    width = 7
    height = 2.25
    fig, ax1 = plt.subplots(figsize=(width, height))

    # Plot Error Probability on the primary y-axis
    sns.lineplot(
        data=df,
        x="intensity",
        y="errorprob",
        ax=ax1,
        color="blue",
        label="Error Probability",
        linewidth=2,
    )
    ax1.set_xlabel("Noise Intensity (%)", fontsize=14)
    ax1.set_ylabel("Error Probability", fontsize=14)
    ax1.tick_params(axis="y")
    ax1.set_ylim(-0.01, 0.51)

    ax1.set_yticks(np.arange(0, 0.51, 0.1))

    # Plot Channel Capacity on the secondary y-axis
    ax2 = ax1.twinx()
    sns.lineplot(
        data=df,
        x="intensity",
        y="capacity",
        ax=ax2,
        color="red",
        label="Channel Capacity",
        linewidth=2,
    )
    ax2.set_ylabel("Channel Capacity\n(Kbps)", fontsize=14)
    ax2.tick_params(axis="y")

    ax2.set_ylim(0, 30)

    ax1.tick_params(axis="y", labelsize=12)
    ax2.tick_params(axis="y", labelsize=12)

    ax1.tick_params(axis="x", labelsize=12)

    # Add a single legend for both lines
    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    fig.legend(
        lines,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.05),
        ncol=2,
        frameon=False,
        fontsize=12,
    )

    # add line on x = 1
    plt.axvline(x=1, color="darkorange", linestyle="--", linewidth=2)
    # add text on orange line that says 10x rotated 90
    txt_height = 20
    plt.text(
        2,
        txt_height,
        r"10$\times$",
        color="darkorange",
        fontsize=12,
        rotation=90,
    )
    plt.axvline(x=87.5, color="purple", linestyle="--", linewidth=2)

    ax1.set_xlim(0, 100)

    # remove legend
    leg1 = ax1.get_legend()
    if leg1:
        leg1.remove()
    leg2 = ax2.get_legend()
    if leg2:
        leg2.remove()

    plt.tight_layout()

    plt.savefig(str(out_path), dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("PRAC Noise Results:")
    interest_pt = 88
    channel_cap_entry = df[
        (df["intensity"] >= interest_pt - 1)
        & (df["intensity"] <= interest_pt + 1)
    ]["capacity"]
    cap_88 = channel_cap_entry.values[0]
    print("88%-Intensity Channel Capacity: " + str(cap_88))

    interest_pt = 1
    channel_cap_entry = df[
        (df["intensity"] >= interest_pt - 1)
        & (df["intensity"] <= interest_pt + 1)
    ]["capacity"]
    cap_lowest = channel_cap_entry.values[0]
    print("Lowest-Intensity Channel Capacity: " + str(cap_lowest))

    return {"capacity_88pct": cap_88, "capacity_lowest": cap_lowest}


if __name__ == "__main__":
    if len(sys.argv) > 3:
        plot(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    else:
        print(
            "Usage: python noise_prac.py <input_file_name> <figure_name> "
            "<number_of_bytes>"
        )
        sys.exit(1)
