"""Runs the latency profile for every defense a config lists.

Example:
    python -m leakyhammer.experiments.latency_profile.run --config default
"""

import argparse
import sys
from typing import Optional, Sequence

from leakyhammer import results
from leakyhammer.experiments.latency_profile.main import (
    EXPERIMENT,
    load_config,
    run_profile,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config", required=True, help="config name or YAML path"
    )
    parser.add_argument(
        "--batch", default=None, help="batch name (default: config name)"
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    batch = results.batch_dir(EXPERIMENT, args.batch or config.name)
    status = 0
    for variant in config.variants:
        record = run_profile(variant, batch)
        print(f"{record['trial']}: {record['status']}")
        if record["status"] != "ok":
            print(record["error"], file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
