"""RFM proof-of-concept covert channel plot (paper figure 6)."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt
import pandas as pd

PathLike = Union[str, Path]


def plot(log_path: PathLike, out_path: PathLike) -> None:
    """Plot the RFM POC: RFMs seen per window over the sent-bit shading.

    Args:
        log_path: Path to the POC log with "[RECV] Received: <bit>
            (<n> RFMs)" lines.
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
    df_acts = pd.DataFrame(columns=["index", "RFM"])
    it = 0

    with open(file_name, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "[RECV] Received" in line:
                try:
                    # format: [RECV] Received: <bit> (<num_rfm> RFMs)
                    bit = int(line.split("Received: ")[1].split("(")[0].strip())
                    num_rfm = int(line.split("(")[1].split(" ")[0].strip())
                    df_acts = pd.concat(
                        [
                            df_acts,
                            pd.DataFrame(
                                [{"index": it, "RFM": num_rfm, "Bit": bit}]
                            ),
                        ],
                        ignore_index=True,
                    )
                    it += 1
                except (IndexError, ValueError):
                    continue

    df = df_acts.copy()
    fig, ax = plt.subplots(figsize=(9, 3.6))

    plt.rcParams.update({"font.size": 14})

    for i, value in enumerate(df["Bit"]):
        color = "sandybrown" if value == 0 else "cornflowerblue"
        ax.axvspan(
            i - 0.5,
            i + 0.5,
            color=color,
            alpha=0.3,
            label="0" if value == 0 else "1",
        )

    ax.plot(df["index"], df["RFM"], marker="o", color="black", label="RFM")

    # Set x-ticks to align with bold lines
    xticks_positions = [(i - 1) + 0.5 for i in range(0, len(df) + 1, 8)]
    ax.set_xticks(xticks_positions)
    ax.set_xticklabels(
        [str(int(pos + 0.5)) for pos in xticks_positions], fontsize=12
    )

    ax.set_xlabel("Transmission Window", fontsize=14)
    ax.set_ylabel("Number of RFMs\nMeasured by the Receiver", fontsize=14)

    for i in range(0, len(df) + 1, 8):
        ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

    # Label each byte of the message under its eight windows
    for idx, ch in enumerate("MICRO"):
        x_pos = (xticks_positions[idx] + xticks_positions[idx + 1]) / 2
        ax.text(
            x_pos,
            -0.5,
            f"({ch})",
            ha="center",
            va="top",
            fontsize=16,
            color="red",
        )

    ax.axhline(3, color="gray", linewidth=2, linestyle="--")

    # Add legend with title inline
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))  # Remove duplicates
    by_label.pop("RFM")  # Remove RFM from legend
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
        bbox_to_anchor=(0.5, 1.2),
        edgecolor="black",
        borderpad=0.3,
        fancybox=False,
        labelspacing=0.5,
    )
    plt.xlim(-1, len(df))

    plt.tight_layout()
    plt.savefig(figure_name, bbox_inches="tight", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        plot(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python poc_rfm.py <input_file_name> <figure_name>")
        sys.exit(1)
