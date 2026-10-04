"""DREAM-C proof-of-concept sanity plot (spike counts per window)."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import pandas as pd

PathLike = Union[str, Path]

# (spikes, sent, recv, expected_msg, decoded_msg, ber, bit_err, bit_total)
_ParsedLog = Tuple[
    List[int],
    List[int],
    List[int],
    str,
    str,
    Optional[float],
    Optional[int],
    Optional[int],
]


def _parse_dream_poc_log(path: str) -> _ParsedLog:
    """Parse the DREAM POC log.

    Args:
        path: Path to the DREAM POC log (output of
            ``poc-scripts/dream_poc_utece.sh``).

    Returns:
        Tuple of (spike_counts, sent_bits, recv_bits, expected_msg,
        decoded_msg, ber, bit_err, bit_total). The three sequences have
        equal length (one entry per transmission window).

    Raises:
        RuntimeError: If the spike counts or sent/received bits are missing.
    """
    spike_counts = None
    sent_bits = None
    recv_bits = None
    expected_msg = None
    decoded_msg = None
    bit_err = None
    bit_total = None
    ber = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "[DREAM-POC-RECV] Spike counts:" in line:
                tail = line.split("Spike counts:", 1)[1].strip()
                spike_counts = [int(x) for x in tail.split() if x != ""]
            elif "[DREAM-POC-SEND] Binary:" in line:
                tail = line.split("Binary:", 1)[1].strip()
                sent_bits = [int(c) for c in tail if c in "01"]
            elif "[DREAM-POC-RECV] Binary:" in line:
                tail = line.split("Binary:", 1)[1].strip()
                recv_bits = [int(c) for c in tail if c in "01"]
            elif "[DREAM-POC-RECV] expected_msg:" in line:
                tail = line.split("expected_msg:", 1)[1]
                if "'" in tail:
                    expected_msg = tail.split("'")[1]
            elif "[DREAM-POC-RECV] Decoded ASCII:" in line:
                tail = line.split("Decoded ASCII:", 1)[1]
                if "'" in tail:
                    decoded_msg = tail.split("'")[1]
            elif "[DREAM-POC-RECV] Bit errors:" in line:
                tail = line.split("Bit errors:", 1)[1].strip()
                lhs, _rhs = tail.split("(")
                num, den = [int(x.strip()) for x in lhs.split("/")]
                bit_err, bit_total = num, den
                ber = num / den if den else None
    if spike_counts is None or sent_bits is None or recv_bits is None:
        raise RuntimeError(
            f"Could not extract POC data from {path}; missing one of "
            "Spike counts / SEND Binary / RECV Binary lines."
        )
    n = min(len(spike_counts), len(sent_bits), len(recv_bits))
    return (
        spike_counts[:n],
        sent_bits[:n],
        recv_bits[:n],
        expected_msg or "?",
        decoded_msg or "?",
        ber,
        bit_err,
        bit_total,
    )


def plot(log_path: PathLike, out_path: PathLike) -> None:
    """Plot the DREAM-C POC: spike counts over sent-bit shading.

    Shows the sent bit as background shading, the receiver's per-window
    spike count as a line, red 'x' markers at bit errors, and per-character
    labels along the x-axis. Prints "Wrote <out_path>" when done.

    Args:
        log_path: Path to the DREAM POC log.
        out_path: Where to save the figure.
    """
    with warnings.catch_warnings(), plt.rc_context():
        warnings.filterwarnings("ignore")
        _plot(str(log_path), str(out_path))


def _plot(in_path: str, out_path: str) -> None:
    """Render the figure (body of :func:`plot`).

    Args:
        in_path: Input log path.
        out_path: Output figure path.
    """
    spikes, sent, recv, expected, decoded, ber, bit_err, bit_total = (
        _parse_dream_poc_log(in_path)
    )
    n = len(spikes)
    df = pd.DataFrame(
        {
            "index": list(range(n)),
            "Spikes": spikes,
            "SentBit": sent,
            "RecvBit": recv,
            "Error": [s != r for s, r in zip(sent, recv)],
        }
    )

    fig, ax = plt.subplots(figsize=(9, 3.6))
    plt.rcParams.update({"font.size": 14})

    for i, value in enumerate(df["SentBit"]):
        color = "sandybrown" if value == 0 else "cornflowerblue"
        ax.axvspan(
            i - 0.5,
            i + 0.5,
            color=color,
            alpha=0.3,
            label=("0" if value == 0 else "1"),
        )

    ax.plot(
        df["index"], df["Spikes"], marker="o", color="black", label="Spikes"
    )

    err_df = df[df["Error"]]
    if len(err_df) > 0:
        ax.scatter(
            err_df["index"],
            err_df["Spikes"],
            marker="x",
            s=110,
            linewidths=2.5,
            color="red",
            zorder=5,
            label="Bit error",
        )

    chars_per_byte = 8
    n_chars = max(1, n // chars_per_byte)
    xticks_positions = [(i - 1) + 0.5 for i in range(0, n + 1, chars_per_byte)]
    ax.set_xticks(xticks_positions)
    ax.set_xticklabels(
        [str(int(pos + 0.5)) for pos in xticks_positions], fontsize=12
    )

    ax.set_xlabel("Transmission Window", fontsize=14)
    ax.set_ylabel("Spike Counts (Receiver)", fontsize=14, labelpad=6)

    for i in range(0, n + 1, chars_per_byte):
        ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

    for c_idx in range(n_chars):
        if c_idx >= len(expected):
            break
        if c_idx + 1 >= len(xticks_positions):
            break
        x_center = (xticks_positions[c_idx] + xticks_positions[c_idx + 1]) / 2
        ax.text(
            x_center,
            -0.45,
            f"({expected[c_idx]})",
            ha="center",
            va="top",
            fontsize=16,
            color="red",
        )

    handles, labels = ax.get_legend_handles_labels()
    by_label = {}
    for h, lab in zip(handles, labels):
        if lab not in by_label:
            by_label[lab] = h
    by_label.pop("Spikes", None)
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
        bbox_to_anchor=(0.5, 1.22),
        edgecolor="black",
        borderpad=0.3,
        fancybox=False,
        labelspacing=0.5,
    )

    if ber is not None and bit_err is not None and bit_total is not None:
        annotation = (
            f"Sent: '{expected}'   Decoded: '{decoded}'   "
            f"Errors: {bit_err}/{bit_total} ({ber * 100:.1f}% BER)"
        )
        ax.text(
            0.5,
            -0.32,
            annotation,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=11,
            color="black",
        )

    plt.xlim(-1, n)
    if df["Spikes"].max() <= 3:
        ax.set_ylim(-0.2, max(3, df["Spikes"].max()) + 0.6)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", pad_inches=0.25, dpi=300)
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 poc_dream.py <input_txt> <output_fig>")
        sys.exit(1)
    plot(sys.argv[1], sys.argv[2])
