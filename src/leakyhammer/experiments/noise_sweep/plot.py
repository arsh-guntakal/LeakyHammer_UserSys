"""Tables, CSVs and figures for a finished noise sweep.

Example:
    python -m leakyhammer.experiments.noise_sweep.plot --config default
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib

# Headless-safe; must be selected before pyplot is first imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from leakyhammer import metrics, results
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


def capacity_by_rate(frame: pd.DataFrame, msg_bytes: int) -> pd.DataFrame:
    """Returns mean error rate, raw rate and capacity at each noise rate.

    One row per distinct "rate" in "frame" (0 is the no-noise baseline),
    averaged over the data patterns. Capacity is computed from the mean error
    rate, as in "metrics.summarize".
    """
    num_bits = msg_bytes * 8
    rows = []
    for rate, group in frame[frame["errors"] >= 0].groupby("rate"):
        ber = group["errors"].mean() / num_bits
        raw = metrics.raw_kbps(num_bits, group["time"].mean())
        rows.append(
            {
                "rate": int(rate),
                "ber": ber,
                "raw_kbps": raw,
                "capacity_kbps": metrics.capacity_kbps(raw, ber),
            }
        )
    return pd.DataFrame(
        rows, columns=["rate", "ber", "raw_kbps", "capacity_kbps"]
    )


def plot_capacity(
    frame: pd.DataFrame,
    out_path: Union[str, Path],
    msg_bytes: int,
    title: str,
) -> Dict[int, float]:
    """Plots error rate and capacity against the background-noise rate.

    The x axis is the noise generator's rate in activations per window, as
    measured (0 is no noise); nothing is normalized or annotated beyond the
    data. Returns the capacity in Kbps at each rate.

    - frame: rows with columns rate, errors and time (see "frame").
    - out_path: where to save the figure.
    - msg_bytes: message length in bytes, used for the bit rate.
    - title: what the figure shows, e.g. the variant's label.
    """
    curve = capacity_by_rate(frame, msg_bytes)
    fig, ax1 = plt.subplots(figsize=(7, 2.6))
    ax1.plot(
        curve["rate"],
        curve["ber"],
        color="blue",
        marker="o",
        linewidth=2,
        label="Error rate",
    )
    ax1.set_xlabel("Noise rate (activations per window)", fontsize=12)
    ax1.set_ylabel("Error rate", fontsize=12)
    ax1.set_ylim(-0.01, 0.51)

    ax2 = ax1.twinx()
    ax2.plot(
        curve["rate"],
        curve["capacity_kbps"],
        color="red",
        marker="s",
        linewidth=2,
        label="Capacity",
    )
    ax2.set_ylabel("Capacity (Kbps)", fontsize=12)
    ax2.set_ylim(0, max(curve["raw_kbps"].max(), 1) * 1.05)

    lines = ax1.get_lines() + ax2.get_lines()
    fig.legend(
        lines,
        [line.get_label() for line in lines],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.08),
        ncol=2,
        frameon=False,
        fontsize=11,
    )
    ax1.set_title(title, fontsize=11, pad=24)
    plt.tight_layout()
    plt.savefig(str(out_path), dpi=300, bbox_inches="tight")
    plt.close(fig)
    return dict(zip(curve["rate"], curve["capacity_kbps"]))


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
        if noisy:
            frame(noisy).to_csv(
                out / f"noise_ber_{variant.name}.csv", index=False
            )
        usable = [r for r in records if r["status"] == "ok"]
        if figures and len({r["params"]["noise_rate"] for r in usable}) > 1:
            plot_capacity(
                frame(usable),
                out / f"noise_{variant.name}.pdf",
                config.msg_bytes,
                variant.label,
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
