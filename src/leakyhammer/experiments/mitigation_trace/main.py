"""One mitigation-trace trial: count DREAM-C's own record of mitigating.

The DREAM-C plugin prints a line every time it issues a DRFMab, independent
of the covert-channel attack's receiver. Counting those lines over a message
of known content answers a narrower question than BER: not "can an attacker
decode this", but "does the plugin mitigate deterministically, in proportion
to how many windows the sender actually hammers". Also defines the config
"run.py" and "plot.py" share.

Example:
    python -m leakyhammer.experiments.mitigation_trace.main --pattern 0xFF
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from leakyhammer import defenses, results, sim
from leakyhammer.config import load_yaml_config

EXPERIMENT = "mitigation_trace"
"""Directory name under the results root."""

CONFIG_DIR = Path(__file__).parent / "configs"
"""Where named configs live."""

_CONFIG_KEYS = {"threshold", "patterns", "msg_bytes"}

_MITIGATION_LINE = re.compile(r"\[Ramulator::DREAM\] T_TH hit:")
"""The plugin's own log line for issuing one DRFMab; see dream.cpp."""

_PREAMBLE_ACTIVE_WINDOWS = 8
"""DREAM_ACTIVE_WINDOWS in "dream_attack.hh": a calibration preamble the
sender hammers through for every message, whatever its content."""


@dataclass(frozen=True)
class MitigationConfig:
    """Which data patterns to send at a fixed DREAM-C threshold.

    - name (str): batch name (the config file's stem).
    - threshold (int): the DCT threshold (T_TH) every trial uses.
    - patterns (tuple[str, ...]): data bytes to repeat, as hex strings.
    - msg_bytes (int): message length in bytes (8 bits each).
    """

    name: str
    threshold: int
    patterns: Tuple[str, ...]
    msg_bytes: int


def load_config(config: Union[str, Path]) -> MitigationConfig:
    """Loads a mitigation-trace config by name or by file path."""
    name, raw = load_yaml_config(config, CONFIG_DIR, _CONFIG_KEYS)
    if not raw.get("patterns"):
        raise ValueError(f"{name}: 'patterns' must list at least one entry")
    return MitigationConfig(
        name,
        int(raw.get("threshold", 40)),
        tuple(str(p) for p in raw["patterns"]),
        int(raw.get("msg_bytes", 100)),
    )


def count_mitigations(log_path: Union[str, Path]) -> int:
    """Returns how many DRFMab commands the plugin's own log reports."""
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    return len(_MITIGATION_LINE.findall(text))


def hammering_windows(pattern: str, msg_bytes: int) -> int:
    """Returns how many windows of the send the sender actually hammers.

    Every send includes a fixed calibration preamble the sender hammers
    through regardless of the message (see "_PREAMBLE_ACTIVE_WINDOWS"), plus
    one window per 1-bit of the message itself.
    """
    ones = bin(int(pattern, 16) & 0xFF).count("1") * msg_bytes
    return _PREAMBLE_ACTIVE_WINDOWS + ones


def trial_name(threshold: int, pattern: str) -> str:
    """Returns a trial's directory name."""
    return f"threshold{threshold}_p{pattern}"


def run_trial(
    threshold: int,
    pattern: str,
    msg_bytes: int,
    batch: Path,
    force: bool = False,
) -> Dict[str, Any]:
    """Runs one trial and stores its record; returns the record.

    A crashed simulation is recorded as failed rather than raised, so one bad
    trial does not lose the rest of a sweep.
    """
    name = trial_name(threshold, pattern)
    out_dir = batch / name
    existing = results.load_record(out_dir)
    if not force and existing is not None and existing["status"] == "ok":
        return existing

    defense = defenses.get_defense("dream")
    simulation = sim.sender_only(
        defense,
        pattern,
        msg_bytes,
        out_dir,
        config_overrides={"threshold": threshold, "debug": True},
    )
    record: Dict[str, Any] = {
        "schema": results.SCHEMA_VERSION,
        "experiment": EXPERIMENT,
        "trial": name,
        "status": "failed",
        "error": None,
        "params": {
            "threshold": threshold,
            "pattern": pattern,
            "msg_bytes": msg_bytes,
        },
        "mitigations": None,
        "hammering_windows": None,
        "provenance": results.provenance(
            simulation.config_path,
            simulation.programs,
            simulation.guest_command,
        ),
    }
    try:
        simulation.run()
    except RuntimeError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    else:
        record.update(
            status="ok",
            mitigations=count_mitigations(simulation.log_path),
            hammering_windows=hammering_windows(pattern, msg_bytes),
        )
    results.save_record(out_dir, record)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs one trial from the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--threshold", type=int, default=40)
    parser.add_argument("--pattern", default="0xFF", help="data byte, hex")
    parser.add_argument("--msg-bytes", type=int, default=100)
    parser.add_argument("--batch", default="single")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    batch = results.batch_dir(EXPERIMENT, args.batch)
    record = run_trial(
        args.threshold, args.pattern, args.msg_bytes, batch, args.force
    )
    name = trial_name(args.threshold, args.pattern)
    if record["status"] != "ok":
        print(f"{name}: FAILED: {record['error']}", file=sys.stderr)
        return 1
    print(
        f"{name}: {record['mitigations']} mitigations over "
        f"{record['hammering_windows']} hammering windows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
