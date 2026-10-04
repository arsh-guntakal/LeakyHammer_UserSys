"""The YAML configuration of a noise sweep.

A config lists "variants" (a defense, optionally with plugin parameter
overrides such as DREAM's "threshold") and the shared message parameters. One
config file describes one batch: "run.py" collects exactly its trials and
"plot.py" reads the same file to know which results to look for.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import yaml

from leakyhammer.defenses import Defense, get_defense

CONFIG_DIR = Path(__file__).parent / "configs"
"""Where named configs ("default", "quick", ...) live."""

_TOP_KEYS = {"variants", "patterns", "msg_bytes", "baseline", "noise"}
_VARIANT_KEYS = {"defense", "overrides", "noise_rates"}


@dataclass(frozen=True)
class Variant:
    """One defense configuration in a sweep.

    - defense (str): name in "leakyhammer.defenses.DEFENSES".
    - overrides (tuple[tuple[str, Any], ...]): plugin parameter overrides,
      sorted by key (kept as a tuple so the variant is hashable).
    - noise_rates (tuple[int, ...] | None): overrides the defense's default
      noise rates when set.
    """

    defense: str
    overrides: Tuple[Tuple[str, Any], ...] = ()
    noise_rates: Optional[Tuple[int, ...]] = None

    @property
    def spec(self: "Variant") -> Defense:
        """Returns the defense this variant configures."""
        return get_defense(self.defense)

    @property
    def rates(self: "Variant") -> Tuple[int, ...]:
        """Returns the noise rates swept for this variant."""
        if self.noise_rates is not None:
            return self.noise_rates
        return self.spec.noise_rates

    @property
    def name(self: "Variant") -> str:
        """Returns a file-safe name, e.g. "dream_threshold62"."""
        return "_".join([self.defense] + [f"{k}{v}" for k, v in self.overrides])

    @property
    def label(self: "Variant") -> str:
        """Returns a display label, e.g. "dream[threshold=62]"."""
        if not self.overrides:
            return self.defense
        inner = ",".join(f"{k}={v}" for k, v in self.overrides)
        return f"{self.defense}[{inner}]"


@dataclass(frozen=True)
class SweepConfig:
    """A whole noise sweep.

    - name (str): batch name (the config file's stem).
    - variants (tuple[Variant, ...]): configurations to measure.
    - patterns (tuple[str, ...]): data bytes to send, as hex strings.
    - msg_bytes (int): message length in bytes (8 bits each).
    - baseline (bool): include the no-noise measurement.
    - noise (bool): include the noise-rate measurements.
    """

    name: str
    variants: Tuple[Variant, ...]
    patterns: Tuple[str, ...]
    msg_bytes: int
    baseline: bool
    noise: bool


def _variant(raw: object) -> Variant:
    """Validates and converts one entry of "variants"."""
    if not isinstance(raw, dict) or "defense" not in raw:
        raise ValueError(f"Each variant needs a 'defense' key, got {raw!r}")
    unknown = set(raw) - _VARIANT_KEYS
    if unknown:
        raise ValueError(f"Unknown variant key(s) {sorted(unknown)}")
    spec = get_defense(raw["defense"])
    overrides = tuple(sorted((raw.get("overrides") or {}).items()))
    if overrides and spec.plugin_impl is None:
        raise ValueError(f"Defense '{spec.name}' takes no overrides")
    rates = raw.get("noise_rates")
    return Variant(
        spec.name,
        overrides,
        None if rates is None else tuple(int(r) for r in rates),
    )


def load_config(config: Union[str, Path]) -> SweepConfig:
    """Loads a config by name (from "configs/") or by file path."""
    path = Path(config)
    if not path.suffix:
        path = CONFIG_DIR / f"{config}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No sweep config at {path}")
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    unknown = set(raw) - _TOP_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown key(s) {sorted(unknown)}")
    if not raw.get("variants"):
        raise ValueError(f"{path}: 'variants' must list at least one entry")
    patterns = tuple(str(p) for p in raw.get("patterns", ["0x55"]))
    cfg = SweepConfig(
        name=path.stem,
        variants=tuple(_variant(v) for v in raw["variants"]),
        patterns=patterns,
        msg_bytes=int(raw.get("msg_bytes", 100)),
        baseline=bool(raw.get("baseline", True)),
        noise=bool(raw.get("noise", True)),
    )
    if not (cfg.baseline or cfg.noise):
        raise ValueError(f"{path}: need 'baseline' and/or 'noise' enabled")
    names = [v.name for v in cfg.variants]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: duplicate variants {names}")
    return cfg
