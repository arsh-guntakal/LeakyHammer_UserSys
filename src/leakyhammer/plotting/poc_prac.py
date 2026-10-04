"""PRAC proof-of-concept covert channel plot (paper figure 3)."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
import pandas as pd

PathLike = Union[str, Path]


def plot(log_path: PathLike, out_path: PathLike) -> None:
    """Plot the PRAC POC: sent bits as shading, received bits as a line.

    Args:
        log_path: Path to the POC log with "[SEND] Binary:" and
            "[RECV] Binary:" lines.
        out_path: Where to save the figure.
    """
    with warnings.catch_warnings(), plt.rc_context():
        warnings.filterwarnings("ignore")
        _plot(str(log_path), str(out_path))


def _plot(file_name: str, figure_name: str) -> None:
    """Render the figure (body of :func:`plot`).

    Args:
        file_name: Input log path.
        figure_name: Output figure path.
    """
    with open(file_name, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    df_receiver = pd.DataFrame(columns=["index", "recv"])
    df_sender = pd.DataFrame(columns=["index", "value"])

    for line in lines:
        if "[SEND] Binary:" in line:
            sender = line.split("[SEND] Binary:")[1].strip()
            for i in range(len(sender)):
                df_sender = pd.concat(
                    [
                        df_sender,
                        pd.DataFrame([{"index": i, "value": int(sender[i])}]),
                    ],
                    ignore_index=True,
                )
        elif "[RECV] Binary:" in line:
            receiver = line.split("[RECV] Binary:")[1].strip()
            for i in range(len(receiver)):
                df_receiver = pd.concat(
                    [
                        df_receiver,
                        pd.DataFrame([{"index": i, "recv": int(receiver[i])}]),
                    ],
                    ignore_index=True,
                )

    df = pd.merge(df_sender, df_receiver, on="index", how="outer")

    fig, ax = plt.subplots(figsize=(9, 4))

    plt.rcParams.update({"font.size": 14})

    for i, value in enumerate(df["value"]):
        color = "sandybrown" if value == 0 else "cornflowerblue"
        ax.axvspan(
            i - 0.5,
            i + 0.5,
            color=color,
            alpha=0.3,
            label="0" if value == 0 else "1",
        )

    ax.plot(df["index"], df["recv"], marker="o", color="black", label="recv")

    # Set x-ticks to align with bold lines
    xticks_positions = [(i - 1) + 0.5 for i in range(0, len(df) + 1, 8)]
    ax.set_xticks(xticks_positions)
    ax.set_xticklabels(
        [str(int(pos + 0.5)) for pos in xticks_positions], fontsize=12
    )

    ax.set_xlabel("Transmission Window", fontsize=14)
    ax.set_ylabel("Back-Off Detected by Receiver", fontsize=14)

    plt.yticks(fontsize=12)

    for i in range(0, len(df) + 1, 8):
        ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

    # Label each byte of the message under its eight windows
    for idx, ch in enumerate("MICRO"):
        x_pos = (xticks_positions[idx] + xticks_positions[idx + 1]) / 2
        ax.text(
            x_pos,
            -0.17,
            f"({ch})",
            ha="center",
            va="top",
            fontsize=16,
            color="red",
        )

    # Add legend with title inline
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))  # Remove duplicates
    by_label.pop("recv")  # Remove recv from legend
    legend_labels = ["Bit Value", *list(by_label.keys())]
    legend_handles = [
        plt.Line2D([0], [0], color="none"),
        *list(by_label.values()),
    ]
    ax.legend(
        legend_handles,
        legend_labels,
        loc="upper center",
        fontsize=12,
        ncol=len(legend_labels),
        framealpha=1,
        bbox_to_anchor=(0.5, 1.15),
        edgecolor="black",
        borderpad=0.3,
        fancybox=False,
        labelspacing=0.5,
    )

    plt.ylim(-0.15, 1.15)
    plt.yticks([0, 1], ["0", "1"], fontsize=12)

    plt.xlim(-1, len(df))

    plt.tight_layout()
    plt.savefig(figure_name, bbox_inches="tight", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        plot(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python poc_prac.py <input_file_name> <figure_name>")
        sys.exit(1)
