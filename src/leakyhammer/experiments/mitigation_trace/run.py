"""Runs every pattern a config lists, in parallel.

Example:
    python -m leakyhammer.experiments.mitigation_trace.run --config default
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence

from leakyhammer import results
from leakyhammer.experiments.mitigation_trace.main import (
    EXPERIMENT,
    load_config,
    run_trial,
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
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    batch = results.batch_dir(EXPERIMENT, args.batch or config.name)
    with ThreadPoolExecutor(max_workers=len(config.patterns)) as pool:
        records = list(
            pool.map(
                lambda p: run_trial(
                    config.threshold, p, config.msg_bytes, batch, args.force
                ),
                config.patterns,
            )
        )
    status = 0
    for record in records:
        print(f"{record['trial']}: {record['status']}")
        if record["status"] != "ok":
            print(f"  {record['error']}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
