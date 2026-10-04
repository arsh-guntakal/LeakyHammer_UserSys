"""Runs the proof of concept for one or more defenses.

Examples:
    python -m leakyhammer.experiments.poc.run --defense rfm dream
    python -m leakyhammer.experiments.poc.run --defense dream --set threshold=62
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Sequence

import yaml

from leakyhammer import results
from leakyhammer.defenses import DEFENSES, get_defense
from leakyhammer.experiments.poc.main import EXPERIMENT, plot_trial, run_poc


def parse_overrides(pairs: Sequence[str]) -> Dict[str, Any]:
    """Parses "key=value" strings; values are read as YAML scalars."""
    overrides: Dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"Expected key=value, got '{pair}'")
        overrides[key] = yaml.safe_load(value)
    return overrides


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--defense",
        nargs="+",
        default=sorted(DEFENSES),
        help="defenses to run (default: all)",
    )
    parser.add_argument(
        "--set",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="plugin parameter overrides, applied to every defense given",
    )
    parser.add_argument("--batch", default="default")
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args(argv)

    overrides = parse_overrides(args.set)
    batch = results.batch_dir(EXPERIMENT, args.batch)
    defenses = [get_defense(name) for name in args.defense]

    # Simulations run in parallel; figures are drawn afterwards, one at a
    # time, because matplotlib's pyplot is not thread-safe.
    with ThreadPoolExecutor(max_workers=len(defenses)) as pool:
        records = list(
            pool.map(lambda d: run_poc(d, batch, overrides), defenses)
        )
    status = 0
    for defense, record in zip(defenses, records):
        if record["status"] == "ok":
            if not args.no_figure:
                plot_trial(defense, batch, overrides)
            print(
                f"{record['trial']:<24} sent {record['sent_text']!r} "
                f"decoded {record['decoded_text']!r} "
                f"errors {record['errors']}/40 (BER {record['ber']:.3f})"
            )
        else:
            print(f"{record['trial']:<24} FAILED: {record['error']}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
