"""Figures for finished proof-of-concept runs, one per defense in a config.

Example:
    python -m leakyhammer.experiments.poc.plot --config default
"""

import argparse
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import matplotlib

# Headless-safe; must be selected before pyplot is first imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from leakyhammer import results
from leakyhammer.experiments.poc.main import EXPERIMENT, load_config

FIGURE_FILE = "figure.pdf"
"""Name of the figure written next to each trial's log."""

PathLike = Union[str, Path]


@dataclass(frozen=True)
class _Counts:
    """How a count-per-window figure is labelled.

    - series (str): name of the plotted line, taken from the log's unit.
    - ylabel (str): y-axis label.
    - threshold (float): the receiver's decision threshold, drawn as a line.
    """

    series: str
    ylabel: str
    threshold: float


_COUNTS = {
    "rfm": _Counts("RFM", "Number of RFMs\nMeasured by the Receiver", 3),
    "rrs": _Counts("SWAPs", "Number of Swaps\nMeasured by the Receiver", 0.5),
}
"""Defenses whose receiver reports a count per window ("<n> RFMs/SWAPs")."""

_MESSAGE = "MICRO"
"""The text the PRAC, RFM and RRS proofs of concept send."""


def _legend(ax: plt.Axes, series: str, anchor_y: float) -> None:
    """Draws the bit-value legend, leaving out the data series itself."""
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    by_label.pop(series)
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
        bbox_to_anchor=(0.5, anchor_y),
        edgecolor="black",
        borderpad=0.3,
        fancybox=False,
        labelspacing=0.5,
    )


def _shade_bits(ax: plt.Axes, bits: Sequence[int]) -> None:
    """Shades each transmission window by the bit that was sent."""
    for i, value in enumerate(bits):
        color = "sandybrown" if value == 0 else "cornflowerblue"
        ax.axvspan(
            i - 0.5,
            i + 0.5,
            color=color,
            alpha=0.3,
            label="0" if value == 0 else "1",
        )


def _plot_counts(log: str, out: str, counts: _Counts) -> None:
    """Draws a count-per-window figure (RFM and RRS)."""
    rows: List[dict] = []
    with open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "[RECV] Received" not in line:
                continue
            try:
                # Format: [RECV] Received: <bit> (<count> <unit>)
                bit = int(line.split("Received: ")[1].split("(")[0].strip())
                count = int(line.split("(")[1].split(" ")[0].strip())
            except (IndexError, ValueError):
                continue
            rows.append({"index": len(rows), counts.series: count, "Bit": bit})
    df = pd.DataFrame(rows, columns=["index", counts.series, "Bit"])

    fig, ax = plt.subplots(figsize=(9, 3.6))
    plt.rcParams.update({"font.size": 14})
    _shade_bits(ax, df["Bit"])
    ax.plot(
        df["index"],
        df[counts.series],
        marker="o",
        color="black",
        label=counts.series,
    )

    # Align the x ticks with the bold byte boundaries.
    xticks = [(i - 1) + 0.5 for i in range(0, len(df) + 1, 8)]
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(int(pos + 0.5)) for pos in xticks], fontsize=12)
    ax.set_xlabel("Transmission Window", fontsize=14)
    ax.set_ylabel(counts.ylabel, fontsize=14)
    for i in range(0, len(df) + 1, 8):
        ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

    # Label each byte of the message under its eight windows.
    for idx, ch in enumerate(_MESSAGE):
        if idx < len(xticks) - 1:
            ax.text(
                (xticks[idx] + xticks[idx + 1]) / 2,
                -0.5,
                f"({ch})",
                ha="center",
                va="top",
                fontsize=16,
                color="red",
            )

    ax.axhline(counts.threshold, color="gray", linewidth=2, linestyle="--")
    _legend(ax, counts.series, 1.2)
    plt.xlim(-1, len(df))
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)


def _plot_binary(log: str, out: str) -> None:
    """Draws the PRAC figure: sent bits shaded, received bits as a line."""
    with open(log, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    sent: List[dict] = []
    received: List[dict] = []
    for line in lines:
        if "[SEND] Binary:" in line:
            bits = line.split("[SEND] Binary:")[1].strip()
            sent = [{"index": i, "value": int(b)} for i, b in enumerate(bits)]
        elif "[RECV] Binary:" in line:
            bits = line.split("[RECV] Binary:")[1].strip()
            received = [
                {"index": i, "recv": int(b)} for i, b in enumerate(bits)
            ]
    df = pd.merge(
        pd.DataFrame(sent, columns=["index", "value"]),
        pd.DataFrame(received, columns=["index", "recv"]),
        on="index",
        how="outer",
    )

    fig, ax = plt.subplots(figsize=(9, 4))
    plt.rcParams.update({"font.size": 14})
    _shade_bits(ax, df["value"])
    ax.plot(df["index"], df["recv"], marker="o", color="black", label="recv")

    xticks = [(i - 1) + 0.5 for i in range(0, len(df) + 1, 8)]
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(int(pos + 0.5)) for pos in xticks], fontsize=12)
    ax.set_xlabel("Transmission Window", fontsize=14)
    ax.set_ylabel("Back-Off Detected by Receiver", fontsize=14)
    plt.yticks(fontsize=12)
    for i in range(0, len(df) + 1, 8):
        ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

    for idx, ch in enumerate(_MESSAGE):
        ax.text(
            (xticks[idx] + xticks[idx + 1]) / 2,
            -0.17,
            f"({ch})",
            ha="center",
            va="top",
            fontsize=16,
            color="red",
        )

    _legend(ax, "recv", 1.15)
    plt.ylim(-0.15, 1.15)
    plt.yticks([0, 1], ["0", "1"], fontsize=12)
    plt.xlim(-1, len(df))
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)


# (spikes, sent, recv, expected_msg, decoded_msg, ber, bit_err, bit_total)
_DreamLog = Tuple[
    List[int],
    List[int],
    List[int],
    str,
    str,
    Optional[float],
    Optional[int],
    Optional[int],
]


def _parse_dream_log(path: str) -> _DreamLog:
    """Parses the DREAM proof-of-concept log.

    Returns the per-window spike counts, sent and received bits (equal
    length), the expected and decoded text, and the receiver's own bit-error
    summary. Raises "RuntimeError" if the spike counts or bits are missing.
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


def _plot_dream(log: str, out: str) -> None:
    """Draws the DREAM-C figure: spike counts, red x at each bit error."""
    spikes, sent, recv, expected, decoded, ber, bit_err, bit_total = (
        _parse_dream_log(log)
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
    _shade_bits(ax, df["SentBit"])
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
    xticks = [(i - 1) + 0.5 for i in range(0, n + 1, chars_per_byte)]
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(int(pos + 0.5)) for pos in xticks], fontsize=12)
    ax.set_xlabel("Transmission Window", fontsize=14)
    ax.set_ylabel("Spike Counts (Receiver)", fontsize=14, labelpad=6)
    for i in range(0, n + 1, chars_per_byte):
        ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

    for c_idx in range(n_chars):
        if c_idx >= len(expected) or c_idx + 1 >= len(xticks):
            break
        ax.text(
            (xticks[c_idx] + xticks[c_idx + 1]) / 2,
            -0.45,
            f"({expected[c_idx]})",
            ha="center",
            va="top",
            fontsize=16,
            color="red",
        )

    # Several windows can share a label; keep the first handle of each.
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
        ax.text(
            0.5,
            -0.32,
            f"Sent: '{expected}'   Decoded: '{decoded}'   "
            f"Errors: {bit_err}/{bit_total} ({ber * 100:.1f}% BER)",
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
    plt.savefig(out, bbox_inches="tight", pad_inches=0.25, dpi=300)
    plt.close(fig)


def plot_poc(defense: str, log_path: PathLike, out_path: PathLike) -> None:
    """Draws a defense's proof-of-concept figure from its simulation log.

    Not thread-safe (matplotlib's pyplot has global state): call from one
    thread at a time. Raises "ValueError" for a defense with no figure.
    """
    log, out = str(log_path), str(out_path)
    # Each figure sets rcParams; scope them and silence pandas deprecations.
    with warnings.catch_warnings(), plt.rc_context():
        warnings.filterwarnings("ignore")
        if defense in _COUNTS:
            _plot_counts(log, out, _COUNTS[defense])
        elif defense == "prac":
            _plot_binary(log, out)
        elif defense == "dream":
            _plot_dream(log, out)
        else:
            raise ValueError(f"No proof-of-concept figure for '{defense}'")


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
        plot_poc(variant.defense, trial_dir / "sim.log", out)
        print(f"wrote {out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
