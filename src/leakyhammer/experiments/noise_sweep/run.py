"""Runs a noise sweep: every trial a config describes, in parallel.

Examples:
    python -m leakyhammer.experiments.noise_sweep.run --config quick -j 8
    python -m leakyhammer.experiments.noise_sweep.run --config default --dry-run
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Sequence

from leakyhammer import results
from leakyhammer.experiments.noise_sweep.main import (
    EXPERIMENT,
    Trial,
    load_config,
    run_trial,
    trials,
)

DEFAULT_JOBS = 4
"""Parallel simulations by default; each peaks near 3 GB of RAM."""


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config", required=True, help="config name or YAML path"
    )
    parser.add_argument(
        "--batch", default=None, help="batch name (default: config name)"
    )
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument(
        "--force", action="store_true", help="re-run finished trials"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print each trial's shell command instead of running it",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    batch = results.batch_dir(EXPERIMENT, args.batch or config.name)
    todo = trials(config)

    if args.dry_run:
        for trial in todo:
            print(trial.simulation(batch).shell_command())
        return 0

    print(f"{len(todo)} trials -> {batch} ({args.jobs} parallel)", flush=True)
    failed = []

    def one(trial: Trial) -> dict:
        return run_trial(trial, batch, force=args.force)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(one, t): t for t in todo}
        for done, future in enumerate(as_completed(futures), start=1):
            trial = futures[future]
            record = future.result()
            print(
                f"[{done}/{len(todo)}] {trial.id}: {record['status']}",
                flush=True,
            )
            if record["status"] != "ok":
                failed.append((trial.id, record["error"]))

    for trial_id, error in failed:
        print(f"FAILED {trial_id}: {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
