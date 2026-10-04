"""One latency profile: a single process timing back-to-back memory requests.

Also defines the config that "run.py" and "plot.py" share. Example:

    python -m leakyhammer.experiments.latency_profile.main
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from leakyhammer import results, sim
from leakyhammer.config import load_yaml_config
from leakyhammer.defenses import Variant, parse_variant

EXPERIMENT = "latency_profile"
"""Directory name under the results root."""

CONFIG_DIR = Path(__file__).parent / "configs"
"""Where named configs live."""


@dataclass(frozen=True)
class ProfileConfig:
    """Which defenses to profile.

    - name (str): batch name (the config file's stem).
    - variants (tuple[Variant, ...]): defenses to profile.
    """

    name: str
    variants: Tuple[Variant, ...]


def load_config(config: Union[str, Path]) -> ProfileConfig:
    """Loads a profile config by name (from "configs/") or by file path."""
    name, raw = load_yaml_config(config, CONFIG_DIR, {"variants"})
    if not raw.get("variants"):
        raise ValueError(f"{name}: 'variants' must list at least one entry")
    variants = tuple(parse_variant(v) for v in raw["variants"])
    for variant in variants:
        # The figure's latency bands are PRAC's back-off and refresh stalls.
        if variant.defense != "prac" or variant.overrides:
            raise ValueError(
                f"{name}: only plain 'prac' can be profiled, got "
                f"'{variant.label}'"
            )
    return ProfileConfig(name, variants)


def run_profile(variant: Variant, batch: Path) -> Dict[str, Any]:
    """Runs the profile, stores its record, and returns the record.

    A crashed simulation is recorded as failed rather than raised.
    """
    out_dir = batch / variant.name
    simulation = sim.latency_profile(variant.spec, out_dir)
    record: Dict[str, Any] = {
        "schema": results.SCHEMA_VERSION,
        "experiment": EXPERIMENT,
        "trial": variant.name,
        "status": "ok",
        "error": None,
        "params": {"defense": variant.defense},
        "provenance": results.provenance(
            simulation.config_path, simulation.programs
        ),
    }
    try:
        simulation.run()
    except RuntimeError as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    results.save_record(out_dir, record)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs one latency profile from the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--defense", default="prac")
    parser.add_argument("--batch", default="single")
    args = parser.parse_args(argv)

    variant = parse_variant({"defense": args.defense})
    batch = results.batch_dir(EXPERIMENT, args.batch)
    record = run_profile(variant, batch)
    if record["status"] != "ok":
        print(f"{variant.name}: FAILED: {record['error']}", file=sys.stderr)
        return 1
    print(f"{variant.name}: log at {batch / variant.name / 'sim.log'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
