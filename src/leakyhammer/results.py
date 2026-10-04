"""Storing and loading experiment results.

Layout: "<RESULTS_DIR>/<experiment>/<batch>/<trial>/", where a trial directory
holds the simulation's raw log ("sim.log"), gem5's own output ("m5out/"), and
"result.json" with everything the measurement depends on. Directories are safe
to browse, edit, or delete by hand: a trial without "result.json" is simply
re-run.
"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from leakyhammer import paths
from leakyhammer.metrics import SimResult

RESULT_FILE = "result.json"
"""Name of the per-trial record."""

SCHEMA_VERSION = 1
"""Bumped when "result.json" changes incompatibly."""


def batch_dir(experiment: str, batch: str) -> Path:
    """Returns the directory holding every trial of one batch."""
    return paths.RESULTS_DIR / experiment / batch


def sha256_of(path: Union[str, Path]) -> Optional[str]:
    """Returns the SHA-256 of a file, or None if it does not exist."""
    path = Path(path)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision() -> Optional[str]:
    """Returns "git describe --always --dirty" for the repo, if available."""
    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def provenance(config_path: Path, programs: List[Path]) -> Dict[str, Any]:
    """Returns what a result depends on besides its parameters.

    The checked-in code revision, the exact Ramulator2 config the run used,
    and a hash of every guest program, so a result can be tied to the build
    that produced it.
    """
    return {
        "git": git_revision(),
        "config_sha256": sha256_of(config_path),
        "programs_sha256": {Path(p).name: sha256_of(p) for p in programs},
    }


def transmission_record(
    experiment: str,
    trial: str,
    params: Dict[str, Any],
    result: SimResult,
    provenance: Dict[str, Any],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds the "result.json" content for one transmission trial.

    A failed trial keeps every key (with "status": "failed" and "error") so
    plots can count failures instead of silently dropping them.
    """
    msg_bits = len(result.sent)
    ber = result.errors / msg_bits if result.ok and msg_bits else None
    return {
        "schema": SCHEMA_VERSION,
        "experiment": experiment,
        "trial": trial,
        "status": "ok" if result.ok and error is None else "failed",
        "error": error,
        "params": params,
        "sent": result.sent,
        "received": result.received,
        "txn_time_ns": result.txn_time_ns,
        "errors": result.errors,
        "ber": ber,
        "resyncs": result.resyncs,
        "min_sleep_assert": result.min_sleep_assert,
        "provenance": provenance,
    }


def save_record(trial_dir: Path, record: Dict[str, Any]) -> Path:
    """Writes "result.json" into a trial directory and returns its path."""
    trial_dir.mkdir(parents=True, exist_ok=True)
    path = trial_dir / RESULT_FILE
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def load_record(trial_dir: Path) -> Optional[Dict[str, Any]]:
    """Returns a trial's record, or None if it has none."""
    path = trial_dir / RESULT_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_done(trial_dir: Path) -> bool:
    """Returns whether a trial has a successful record."""
    record = load_record(trial_dir)
    return record is not None and record["status"] == "ok"


def load_batch(directory: Path) -> List[Dict[str, Any]]:
    """Returns every trial record under a batch, sorted by trial name."""
    records = []
    for trial_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
        record = load_record(trial_dir)
        if record is not None:
            records.append(record)
    return records
