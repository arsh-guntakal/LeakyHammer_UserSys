"""One proof-of-concept transmission: a short text message through a defense.

Also defines the config that "run.py" and "plot.py" share. Example:

    python -m leakyhammer.experiments.poc.main --defense dream
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from leakyhammer import results, sim
from leakyhammer.config import load_yaml_config, parse_overrides
from leakyhammer.defenses import Variant, get_defense, parse_variant
from leakyhammer.metrics import parse_poc

EXPERIMENT = "poc"
"""Directory name under the results root."""

CONFIG_DIR = Path(__file__).parent / "configs"
"""Where named configs live."""


@dataclass(frozen=True)
class PocConfig:
    """Which defenses to run the proof of concept against.

    - name (str): batch name (the config file's stem).
    - variants (tuple[Variant, ...]): defenses, optionally with overrides.
    """

    name: str
    variants: Tuple[Variant, ...]


def load_config(config: Union[str, Path]) -> PocConfig:
    """Loads a POC config by name (from "configs/") or by file path."""
    name, raw = load_yaml_config(config, CONFIG_DIR, {"variants"})
    if not raw.get("variants"):
        raise ValueError(f"{name}: 'variants' must list at least one entry")
    variants = tuple(parse_variant(v) for v in raw["variants"])
    if len({v.name for v in variants}) != len(variants):
        raise ValueError(f"{name}: duplicate variants")
    return PocConfig(name, variants)


def run_poc(variant: Variant, batch: Path) -> Dict[str, Any]:
    """Runs the variant's POC, stores its record, and returns the record.

    A crashed simulation or an undecodable log is recorded as failed (with
    its error) rather than raised. Safe to call from several threads.
    """
    out_dir = batch / variant.name
    simulation = sim.poc(variant.spec, out_dir, dict(variant.overrides))
    record: Dict[str, Any] = {
        "schema": results.SCHEMA_VERSION,
        "experiment": EXPERIMENT,
        "trial": variant.name,
        "status": "failed",
        "error": None,
        "params": {
            "defense": variant.defense,
            "overrides": dict(variant.overrides),
            "options": variant.spec.poc_options,
        },
        "sent_text": None,
        "decoded_text": None,
        "errors": None,
        "ber": None,
        "resyncs": None,
        "provenance": results.provenance(
            simulation.config_path, simulation.programs
        ),
    }
    try:
        simulation.run()
        decoded = parse_poc(simulation.log_path)
    except (RuntimeError, ValueError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    else:
        record.update(
            status="ok",
            sent_text=decoded.sent_text,
            decoded_text=decoded.decoded_text,
            errors=decoded.errors,
            ber=decoded.ber,
            resyncs=decoded.resyncs,
        )
    results.save_record(out_dir, record)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs one proof of concept from the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--defense", required=True)
    parser.add_argument(
        "--set",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="plugin parameter overrides",
    )
    parser.add_argument("--batch", default="single")
    args = parser.parse_args(argv)

    overrides = parse_overrides(args.set)
    spec = get_defense(args.defense)
    variant = parse_variant({"defense": spec.name, "overrides": overrides})
    record = run_poc(variant, results.batch_dir(EXPERIMENT, args.batch))
    if record["status"] != "ok":
        print(f"{variant.name}: FAILED: {record['error']}", file=sys.stderr)
        return 1
    print(
        f"{variant.name}: sent {record['sent_text']!r} decoded "
        f"{record['decoded_text']!r}, errors {record['errors']}/40 "
        f"(BER {record['ber']:.3f})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
