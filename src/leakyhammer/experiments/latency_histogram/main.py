"""One latency-histogram measurement: what a probing process sees, by sent bit.

A sender transmits a repeating data byte while a diagnostic receiver, which
decodes nothing, histograms the latency of its memory probes in every window.
Also defines the config that "run.py" and "plot.py" share. Example:

    python -m leakyhammer.experiments.latency_histogram.main --defense rfm \
        --probe-rows 1 --first-row 1 --bank-group 7 --bank 3
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from leakyhammer import paths, results, sim
from leakyhammer.config import load_yaml_config, parse_overrides
from leakyhammer.defenses import Variant, get_defense, parse_variant

EXPERIMENT = "latency_histogram"
"""Directory name under the results root."""

CONFIG_DIR = Path(__file__).parent / "configs"
"""Where named configs live."""

NORMAL_SYNC_NS = 220000
"""When most senders start their first window, in ns."""

_CONFIG_KEYS = {"variants", "pattern", "msg_bytes"}
_VARIANT_KEYS = {
    "tag",
    "probe_rows",
    "first_row",
    "bank_group",
    "bank",
    "sync_ns",
}


@dataclass(frozen=True)
class HistVariant(Variant):
    """A defense and where the diagnostic receiver probes.

    - tag (str): distinguishes variants of the same defense in file names.
    - probe_rows (int): distinct rows probed round-robin.
    - first_row (int): the first of them.
    - bank_group, bank (int): the bank probed, in rank 1.
    - sync_ns (int): when the paired sender starts its first window.
    """

    tag: str = ""
    probe_rows: int = 64
    first_row: int = 1000
    bank_group: int = 0
    bank: int = 0
    sync_ns: int = NORMAL_SYNC_NS

    @property
    def name(self: "HistVariant") -> str:
        """Returns a file-safe name, e.g. "rrs_spread"."""
        return "_".join(
            [self.defense]
            + [f"{k}{v}" for k, v in self.overrides]
            + ([self.tag] if self.tag else [])
        )

    @property
    def label(self: "HistVariant") -> str:
        """Returns a display label, e.g. "rrs[spread]"."""
        base = Variant(self.defense, self.overrides).label
        return f"{base}[{self.tag}]" if self.tag else base


@dataclass(frozen=True)
class HistConfig:
    """Which probes to run against which senders.

    - name (str): batch name (the config file's stem).
    - variants (tuple[HistVariant, ...]): senders and probe placements.
    - pattern (str): the data byte the sender repeats, as hex.
    - msg_bytes (int): sender message length; every bit is one window.
    """

    name: str
    variants: Tuple[HistVariant, ...]
    pattern: str
    msg_bytes: int


def _hist_variant(raw: object) -> HistVariant:
    """Converts one entry of "variants" (validated by "parse_variant")."""
    base = parse_variant(raw, _VARIANT_KEYS)
    extra = {k: raw[k] for k in _VARIANT_KEYS if k in raw}
    return HistVariant(base.defense, base.overrides, **extra)


def load_config(config: Union[str, Path]) -> HistConfig:
    """Loads a config by name (from "configs/") or by file path."""
    name, raw = load_yaml_config(config, CONFIG_DIR, _CONFIG_KEYS)
    if not raw.get("variants"):
        raise ValueError(f"{name}: 'variants' must list at least one entry")
    variants = tuple(_hist_variant(v) for v in raw["variants"])
    if len({v.name for v in variants}) != len(variants):
        raise ValueError(f"{name}: duplicate variants (add a 'tag')")
    return HistConfig(
        name,
        variants,
        str(raw.get("pattern", "0x55")),
        int(raw.get("msg_bytes", 10)),
    )


@dataclass
class HistogramLog:
    """A parsed diagnostic-receiver log.

    - edges_ns (list[int]): upper edges of the latency bins; one more bin
      holds everything above the last edge.
    - windows (list[tuple[int, list[int]]]): per window, the sent bit and the
      number of probes in each bin.
    - late_ns (int | None): how late the receiver was for its first window, if
      it was, which means it is misaligned with the sender.
    """

    edges_ns: List[int]
    windows: List[Tuple[int, List[int]]]
    late_ns: Optional[int] = None


def parse_histogram_log(path: Union[str, Path]) -> HistogramLog:
    """Parses the receiver's "[HIST]" lines; raises ValueError if none."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    edges = re.search(r"\[HIST\] edges_ns:((?: \d+)+)", text)
    late = re.search(r"\[HIST\] LATE: .*finished (\d+) ns after", text)
    windows = [
        (int(m.group(1)), [int(x) for x in m.group(2).split()])
        for m in re.finditer(r"\[HIST\] W \d+ sent (\d) :((?: \d+)+)", text)
    ]
    if not edges or not windows:
        raise ValueError(f"{path}: no histogram lines found")
    return HistogramLog(
        [int(x) for x in edges.group(1).split()],
        windows,
        int(late.group(1)) if late else None,
    )


def mean_probes(log: HistogramLog, bit: int) -> List[float]:
    """Returns the mean probes per window in each bin, over windows of "bit"."""
    selected = [counts for sent, counts in log.windows if sent == bit]
    if not selected:
        return [0.0] * (len(log.edges_ns) + 1)
    return [sum(col) / len(selected) for col in zip(*selected)]


def run_trial(
    variant: HistVariant,
    batch: Path,
    pattern: str,
    msg_bytes: int,
    force: bool = False,
) -> Dict[str, Any]:
    """Runs one measurement and stores its record; returns the record.

    A crashed simulation, an unparseable log, or a receiver that started late
    (so its windows do not line up with the sender's) is recorded as failed.
    """
    out_dir = batch / variant.name
    existing = results.load_record(out_dir)
    if not force and existing is not None and existing["status"] == "ok":
        return existing
    probe = (
        f"{variant.probe_rows} {variant.first_row} {variant.bank_group} "
        f"{variant.bank} {variant.sync_ns}"
    )
    simulation = sim.transmission(
        variant.spec,
        pattern,
        msg_bytes,
        out_dir,
        None,
        dict(variant.overrides),
        receiver=paths.ATTACK_BIN_DIR / "latency_histogram",
        receiver_args=probe,
    )
    record: Dict[str, Any] = {
        "schema": results.SCHEMA_VERSION,
        "experiment": EXPERIMENT,
        "trial": variant.name,
        "status": "failed",
        "error": None,
        "params": {
            "defense": variant.defense,
            "overrides": dict(variant.overrides),
            "pattern": pattern,
            "msg_bytes": msg_bytes,
            "probe_rows": variant.probe_rows,
            "first_row": variant.first_row,
            "bank_group": variant.bank_group,
            "bank": variant.bank,
            "sync_ns": variant.sync_ns,
        },
        "edges_ns": None,
        "windows": None,
        "mean_probes": None,
        "provenance": results.provenance(
            simulation.config_path,
            simulation.programs,
            simulation.guest_command,
        ),
    }
    try:
        simulation.run()
        log = parse_histogram_log(simulation.log_path)
        if log.late_ns is not None:
            raise ValueError(
                f"receiver was {log.late_ns} ns late for its first window; "
                "raise sync_ns"
            )
    except (RuntimeError, ValueError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    else:
        record.update(
            status="ok",
            edges_ns=log.edges_ns,
            windows={
                "1": sum(1 for b, _ in log.windows if b == 1),
                "0": sum(1 for b, _ in log.windows if b == 0),
            },
            mean_probes={
                "1": mean_probes(log, 1),
                "0": mean_probes(log, 0),
            },
        )
    results.save_record(out_dir, record)
    return record


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs one measurement from the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--defense", required=True)
    parser.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    parser.add_argument("--pattern", default="0x55")
    parser.add_argument("--msg-bytes", type=int, default=10)
    parser.add_argument("--probe-rows", type=int, default=64)
    parser.add_argument("--first-row", type=int, default=1000)
    parser.add_argument("--bank-group", type=int, default=0)
    parser.add_argument("--bank", type=int, default=0)
    parser.add_argument("--sync-ns", type=int, default=NORMAL_SYNC_NS)
    parser.add_argument("--batch", default="single")
    args = parser.parse_args(argv)

    spec = get_defense(args.defense)
    overrides = tuple(sorted(parse_overrides(args.set).items()))
    variant = HistVariant(
        spec.name,
        overrides,
        probe_rows=args.probe_rows,
        first_row=args.first_row,
        bank_group=args.bank_group,
        bank=args.bank,
        sync_ns=args.sync_ns,
    )
    record = run_trial(
        variant,
        results.batch_dir(EXPERIMENT, args.batch),
        args.pattern,
        args.msg_bytes,
    )
    if record["status"] != "ok":
        print(f"{variant.name}: FAILED: {record['error']}", file=sys.stderr)
        return 1
    print(f"{variant.name}: {record['windows']} windows (sent 1 / sent 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
