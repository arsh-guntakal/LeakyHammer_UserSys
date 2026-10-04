"""Tables, CSVs and figures for a finished noise sweep.

Examples:
    python -m leakyhammer.experiments.noise_sweep.plot --config default
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from leakyhammer import results
from leakyhammer.experiments.noise_sweep.config import (
    SweepConfig,
    Variant,
    load_config,
)
from leakyhammer.experiments.noise_sweep.main import EXPERIMENT, trials
from leakyhammer.metrics import SimResult, Summary, summarize

CSV_COLUMNS = ["rate", "pattern", "sent", "received", "time", "errors"]
"""Columns of the per-defense CSVs, as the plotters read them."""


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
    config: SweepConfig, batch: Path, variant: Variant
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
    """Returns records as a table with the legacy CSV columns."""
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
        if not (noisy and figures):
            if noisy:
                frame(noisy).to_csv(
                    out / f"noise_ber_{variant.name}.csv", index=False
                )
            continue
        csv = out / f"noise_ber_{variant.name}.csv"
        frame(noisy).to_csv(csv, index=False)
        # Imported here so listing/reporting works without matplotlib.
        from leakyhammer.plotting import noise_prac, noise_rfm

        figure = out / f"noise_{variant.name}.pdf"
        if variant.defense == "prac":
            noise_prac.plot(csv, figure, config.msg_bytes)
        else:
            noise_rfm.plot(
                csv, figure, config.msg_bytes, variant.defense.upper()
            )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="default")
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
