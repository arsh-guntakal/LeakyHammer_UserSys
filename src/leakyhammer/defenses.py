"""The RowHammer defenses under test and how to attack each one.

A defense is one entry in "DEFENSES". Adding a defense to every experiment is
adding an entry here, plus its Ramulator plugin/config and its attack
sources (see "docs/adding-a-defense.md").
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Set, Tuple

from leakyhammer import paths

ALL_ROLES = ("sender", "receiver", "poc_sender", "poc_receiver")
"""Programs a defense normally provides, as "<role>.cc" in its directory."""


@dataclass(frozen=True)
class Defense:
    """A RowHammer defense and the attack parameters tuned for it.

    - name (str): short lowercase identifier; used in file names and as the
      prefix of the compiled attack programs ("<name>_sender", ...).
    - config_file (str): Ramulator2 YAML file name in "RAMULATOR_CONFIG_DIR".
    - plugin_impl (str | None): the "impl" of the defense's ControllerPlugin
      in that YAML, which "config_overrides" edit. None if the defense has no
      tunable plugin parameters.
    - txn_period_ns (int): sender/receiver window length per transmitted bit.
    - noise_rates (tuple[int, ...]): noise-generator access rates swept in
      the noise experiments (activations per window).
    - poc_options (str): arguments of the proof-of-concept sender and
      receiver, after the program name.
    - poc_message (str | None): text the POC transmits, when it sends text.
    - roles (tuple[str, ...]): the programs the defense has; a legacy
      defense may have no proof of concept.
    - attack_dir (str | None): directory of its sources under "attacks/"
      (default: its name). If that directory holds its own
      "rowhammer-side.cc" the programs build against it instead of
      "attacks/common/" (see "legacy/").
    - legacy_stem (str | None): the defense's name in the original artifact's
      file names, when that differs from "name".
    """

    name: str
    config_file: str
    txn_period_ns: int
    noise_rates: Tuple[int, ...]
    poc_options: str
    plugin_impl: Optional[str] = None
    poc_message: Optional[str] = None
    roles: Tuple[str, ...] = ALL_ROLES
    attack_dir: Optional[str] = None
    legacy_stem: Optional[str] = None

    @property
    def source_dir(self: "Defense") -> Path:
        """Returns the directory holding the defense's attack sources."""
        return paths.ATTACK_SRC_DIR / (self.attack_dir or self.name)

    @property
    def config_path(self: "Defense") -> Path:
        """Returns the path of the defense's default Ramulator2 config."""
        return paths.RAMULATOR_CONFIG_DIR / self.config_file

    @property
    def sender(self: "Defense") -> Path:
        """Returns the compiled sender program."""
        return paths.ATTACK_BIN_DIR / f"{self.name}_sender"

    @property
    def receiver(self: "Defense") -> Path:
        """Returns the compiled receiver program."""
        return paths.ATTACK_BIN_DIR / f"{self.name}_receiver"

    @property
    def poc_sender(self: "Defense") -> Path:
        """Returns the compiled proof-of-concept sender program."""
        return paths.ATTACK_BIN_DIR / f"{self.name}_poc_sender"

    @property
    def poc_receiver(self: "Defense") -> Path:
        """Returns the compiled proof-of-concept receiver program."""
        return paths.ATTACK_BIN_DIR / f"{self.name}_poc_receiver"


_PRAC_NOISE = (275, 475, 1075, 1975)
"""Endpoints (275, 1975) and the ~88%-intensity knee point (475)."""

_RFM_NOISE = (200, 263, 325)
"""Endpoints (200, 325) and the ~50%-intensity knee point (263)."""

DEFENSES: Dict[str, Defense] = {
    d.name: d
    for d in (
        Defense(
            name="prac",
            config_file="prac.yaml",
            txn_period_ns=25000,
            noise_rates=_PRAC_NOISE,
            poc_options="25000 5 aa",
            poc_message="MICRO",
        ),
        Defense(
            name="rfm",
            config_file="rfm.yaml",
            txn_period_ns=20000,
            noise_rates=_RFM_NOISE,
            poc_options="20000 5 aa",
            poc_message="MICRO",
        ),
        # 20000 ns is the empirically best window for DREAM-C. A 25000 ns
        # window lowered raw rate by 20% and nearly doubled the baseline BER
        # (the receiver's probes self-trigger the shared gang counter), so
        # net capacity dropped from 16.0 to 13.2 Kbps. Do not raise casually.
        Defense(
            name="dream",
            config_file="dream.yaml",
            txn_period_ns=20000,
            noise_rates=_RFM_NOISE,
            poc_options="20000 5 0x00 UTECE",
            plugin_impl="DREAM",
            poc_message="UTECE",
        ),
        # The RFM of the report's baseline row. The commit that measured it
        # (2b847b2) inflated every RFM stall to 5000 cycles, widened the
        # receivers' latency bands and lowered their decision threshold, and
        # was later reverted because it broke the RFM proof of concept. Its
        # programs are kept verbatim in "attacks/legacy/rfm_prerevert" and the
        # inflation is a "timing:" override in "rfm_prerevert.yaml". Do not
        # use it as a model for new defenses.
        Defense(
            name="rfm_prerevert",
            config_file="rfm_prerevert.yaml",
            txn_period_ns=20000,
            noise_rates=_RFM_NOISE,
            poc_options="",
            roles=("sender", "receiver"),
            attack_dir="legacy/rfm_prerevert",
            legacy_stem="rfm",
        ),
        Defense(
            name="rrs",
            config_file="rrs.yaml",
            txn_period_ns=20000,
            noise_rates=_RFM_NOISE,
            poc_options="20000 5 aa",
            plugin_impl="RRS",
            poc_message="MICRO",
        ),
    )
}
"""All defenses, keyed by name."""


def get_defense(name: str) -> Defense:
    """Returns the defense called "name" (case-insensitive)."""
    key = name.lower()
    if key not in DEFENSES:
        raise ValueError(
            f"Unknown defense '{name}'; choose from {sorted(DEFENSES)}"
        )
    return DEFENSES[key]


@dataclass(frozen=True)
class Variant:
    """A defense, optionally with plugin parameters overridden.

    - defense (str): name in "DEFENSES".
    - overrides (tuple[tuple[str, Any], ...]): plugin parameter overrides,
      sorted by key (a tuple so the variant is hashable).
    """

    defense: str
    overrides: Tuple[Tuple[str, Any], ...] = ()

    @property
    def spec(self: "Variant") -> Defense:
        """Returns the defense this variant configures."""
        return get_defense(self.defense)

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


def parse_variant(
    raw: object, extra_keys: Optional[Set[str]] = None
) -> Variant:
    """Validates one "variants" entry of a config and converts it.

    "extra_keys" are additional keys the calling experiment accepts (it reads
    them itself). Unknown keys, unknown defenses, and overrides on a defense
    with no tunable plugin all raise "ValueError".
    """
    if not isinstance(raw, Mapping) or "defense" not in raw:
        raise ValueError(f"Each variant needs a 'defense' key, got {raw!r}")
    unknown = set(raw) - {"defense", "overrides"} - (extra_keys or set())
    if unknown:
        raise ValueError(f"Unknown variant key(s) {sorted(unknown)}")
    spec = get_defense(raw["defense"])
    overrides = tuple(sorted((raw.get("overrides") or {}).items()))
    if overrides and spec.plugin_impl is None:
        raise ValueError(f"Defense '{spec.name}' takes no overrides")
    return Variant(spec.name, overrides)
