"""Runs the proof of concept for every defense a config lists, in parallel.

Examples:
    python -m leakyhammer.experiments.poc.run --config default
    python -m leakyhammer.experiments.poc.run --config dream_threshold
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence

from leakyhammer import results
from leakyhammer.experiments.poc.main import EXPERIMENT, load_config, run_poc


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
    with ThreadPoolExecutor(max_workers=len(config.variants)) as pool:
        records = list(pool.map(lambda v: run_poc(v, batch), config.variants))
    status = 0
    for record in records:
        if record["status"] == "ok":
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
