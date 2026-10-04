"""Tables, CSVs and figures for a finished noise sweep.

Example:
    python -m leakyhammer.experiments.noise_sweep.plot --config default
"""

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib

# Headless-safe; must be selected before pyplot is first imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from leakyhammer import results
from leakyhammer.experiments.noise_sweep.main import (
    EXPERIMENT,
    NoiseVariant,
    SweepConfig,
    load_config,
    trials,
)
from leakyhammer.metrics import SimResult, Summary, summarize

CSV_COLUMNS = ["rate", "pattern", "sent", "received", "time", "errors"]
"""Columns of the per-defense CSVs, as the figure code reads them."""


@dataclass(frozen=True)
class _Style:
    """How a defense's capacity-versus-noise figure is drawn.

    - max_rate (int | None): noise rates at or above this are dropped (RFM's
      10x reference point is at rate 325, so higher rates are off the plot).
    - capacity_ylim (int): top of the capacity axis, in Kbps.
    - capacity_tick_step (int | None): spacing of explicit capacity ticks.
    - label_height (int): height of the "10x" label on its reference line.
    - closed_line (float | None): x of the purple "channel degraded" line, or
      None when the channel is closed at every intensity.
    - knee_pct (int): the intensity at which the capacity is reported.
    """

    max_rate: Optional[int]
    capacity_ylim: int
    capacity_tick_step: Optional[int]
    label_height: int
    closed_line: Optional[float]
    knee_pct: int


_PRAC_STYLE = _Style(None, 30, None, 20, 87.5, 88)
_RFM_STYLE = _Style(350, 50, 10, 35, 50.0, 50)
_STYLES = {
    "prac": _PRAC_STYLE,
    "rfm": _RFM_STYLE,
    "rrs": _RFM_STYLE,
    "dream": replace(_RFM_STYLE, closed_line=None),
}


def plot_capacity(
    csv_path: Union[str, Path],
    out_path: Union[str, Path],
    msg_bytes: int,
    defense: str,
) -> Dict[str, float]:
    """Plots error probability and capacity versus noise intensity.

    Prints a short summary and returns "capacity_at_knee" (capacity near the
    defense's reference intensity, Kbps) and "capacity_lowest" (near 1%).

    - csv_path: noise CSV with columns rate, errors, time, sent, received.
    - out_path: where to save the figure.
    - msg_bytes: message length in bytes, used for the bit rate.
    - defense: "prac", "rfm", "rrs" or "dream"; selects the axis ranges.
    """
    style = _STYLES[defense.lower()]
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
    if style.max_rate is not None:
        df = df[df["rate"] < style.max_rate]

    df["rate"] = df["rate"] - 175

    # Zero error probabilities would make the entropy undefined.
    df.loc[df["errors"] == 0, "errors"] = 0.0001

    df["intensity"] = (
        100
        - (df["rate"].astype(float) - df["rate"].min())
        / (df["rate"].max() - df["rate"].min())
        * 100
    )
    df["errorprob"] = df["errors"] / num_bits

    # The time column is in nanoseconds.
    df["time_s"] = df["time"] / 1e9
    df["rawbitrate"] = num_bits / df["time_s"] / 1024
    df["entropy"] = (-1 * df["errorprob"] * np.log2(df["errorprob"])) - (
        (1 - df["errorprob"]) * np.log2(1 - df["errorprob"])
    )
    df["capacity"] = (1 - df["entropy"]) * df["rawbitrate"]

    fig, ax1 = plt.subplots(figsize=(7, 2.25))

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
    ax2.set_ylim(0, style.capacity_ylim)
    if style.capacity_tick_step is not None:
        ax2.set_yticks(
            np.arange(0, style.capacity_ylim + 1, style.capacity_tick_step)
        )

    ax1.tick_params(axis="y", labelsize=12)
    ax2.tick_params(axis="y", labelsize=12)
    ax1.tick_params(axis="x", labelsize=12)

    # One legend for both lines.
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

    # Reference line at 10x the noise of a heavy multi-core workload.
    plt.axvline(x=1, color="darkorange", linestyle="--", linewidth=2)
    plt.text(
        2,
        style.label_height,
        r"10$\times$",
        color="darkorange",
        fontsize=12,
        rotation=90,
    )
    if style.closed_line is not None:
        plt.axvline(
            x=style.closed_line, color="purple", linestyle="--", linewidth=2
        )

    ax1.set_xlim(0, 100)

    for axis in (ax1, ax2):
        legend = axis.get_legend()
        if legend:
            legend.remove()

    plt.tight_layout()
    plt.savefig(str(out_path), dpi=300, bbox_inches="tight")
    plt.close(fig)

    def capacity_near(intensity: int) -> float:
        """Returns the capacity within 1% of an intensity."""
        band = df[
            (df["intensity"] >= intensity - 1)
            & (df["intensity"] <= intensity + 1)
        ]["capacity"]
        return float(band.values[0])

    knee = capacity_near(style.knee_pct)
    lowest = capacity_near(1)
    print(f"{defense.upper()} Noise Results:")
    print(f"{style.knee_pct}%-Intensity Channel Capacity: {knee}")
    print(f"Lowest-Intensity Channel Capacity: {lowest}")
    return {"capacity_at_knee": knee, "capacity_lowest": lowest}


def _sim_result(record: Dict[str, Any]) -> SimResult:
    """Rebuilds a "SimResult" from a stored record."""
    return SimResult(
        sent=record["sent"],
        received=record["received"],
        txn_time_ns=record["txn_time_ns"],
        errors=record["errors"],
        resyncs=record["resyncs"],
        min_sleep_assert=record["min_sleep_assert"],
    )


def collect(
    config: SweepConfig, batch: Path, variant: NoiseVariant
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Returns the variant's records in config order, and missing trial ids."""
    found: List[Dict[str, Any]] = []
    missing: List[str] = []
    for trial in trials(config):
        if trial.variant != variant:
            continue
        record = results.load_record(batch / trial.id)
        if record is None:
            missing.append(trial.id)
        else:
            found.append(record)
    return found, missing


def frame(records: Sequence[Dict[str, Any]]) -> pd.DataFrame:
    """Returns records as a table with the CSV columns."""
    return pd.DataFrame(
        [
            {
                "rate": r["params"]["noise_rate"],
                "pattern": r["params"]["pattern"],
                "sent": r["sent"],
                "received": r["received"],
                "time": r["txn_time_ns"],
                "errors": r["errors"],
            }
            for r in records
        ],
        columns=CSV_COLUMNS,
    )


def summarize_records(
    records: Sequence[Dict[str, Any]], msg_bytes: int
) -> Optional[Summary]:
    """Returns the aggregate of records, or None when there are none."""
    if not records:
        return None
    return summarize([_sim_result(r) for r in records], msg_bytes * 8)


def report(config: SweepConfig, batch: Path) -> List[str]:
    """Returns the summary table, one line per variant and kind."""
    lines = [
        f"{'variant':<24}{'kind':<10}{'raw Kbps':>10}{'mean BER':>10}"
        f"{'cap Kbps':>10}{'runs':>6}"
    ]
    for variant in config.variants:
        records, missing = collect(config, batch, variant)
        for kind, rate_test in (
            ("baseline", lambda r: r["params"]["noise_rate"] == 0),
            ("noise", lambda r: r["params"]["noise_rate"] > 0),
        ):
            subset = [r for r in records if rate_test(r)]
            try:
                s = summarize_records(subset, config.msg_bytes)
            except ValueError as exc:
                lines.append(f"{variant.label:<24}{kind:<10}  {exc}")
                continue
            if s is None:
                continue
            lines.append(
                f"{variant.label:<24}{kind:<10}{s.raw_kbps:>10.2f}"
                f"{s.ber:>10.4f}{s.capacity_kbps:>10.3f}{len(subset):>6}"
            )
        if missing:
            lines.append(f"{variant.label:<24}missing {len(missing)} trials")
    return lines


def write_outputs(
    config: SweepConfig, batch: Path, out: Path, figures: bool = True
) -> None:
    """Writes per-variant CSVs (and figures) into "out"."""
    out.mkdir(parents=True, exist_ok=True)
    for variant in config.variants:
        records, _ = collect(config, batch, variant)
        base = [r for r in records if r["params"]["noise_rate"] == 0]
        noisy = [r for r in records if r["params"]["noise_rate"] > 0]
        if base:
            frame(base).to_csv(out / f"ber_{variant.name}.csv", index=False)
        if not noisy:
            continue
        csv = out / f"noise_ber_{variant.name}.csv"
        frame(noisy).to_csv(csv, index=False)
        if figures:
            plot_capacity(
                csv,
                out / f"noise_{variant.name}.pdf",
                config.msg_bytes,
                variant.defense,
            )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config", required=True, help="config name or YAML path"
    )
    parser.add_argument("--batch", default=None)
    parser.add_argument(
        "--out", default=None, help="output dir (default: <batch>/analysis)"
    )
    parser.add_argument(
        "--no-figures", action="store_true", help="CSVs and table only"
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    batch = results.batch_dir(EXPERIMENT, args.batch or config.name)
    if not batch.is_dir():
        print(f"No results at {batch}; run the sweep first", file=sys.stderr)
        return 1
    print("\n".join(report(config, batch)))
    out = Path(args.out) if args.out else batch / "analysis"
    write_outputs(config, batch, out, figures=not args.no_figures)
    print(f"wrote CSVs{'' if args.no_figures else ' and figures'} to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
