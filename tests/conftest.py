"""Shared fixtures; fails collection for tests without a marker.

Tests build the logs and tables they need from the builders below, in the
formats the real programs print, instead of reading committed data files.
"""

import dataclasses
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence

import pandas as pd
import pytest
import yaml

from leakyhammer import paths, sim
from leakyhammer.defenses import get_defense
from leakyhammer.metrics import bits_to_text, text_to_bits

MARKERS = {"unit", "integration", "slow", "regression", "experiment"}


def pytest_collection_modifyitems(items: List[pytest.Item]) -> None:
    """Requires every test to carry at least one of our markers."""
    unmarked = [
        item.nodeid
        for item in items
        if not MARKERS & {m.name for m in item.iter_markers()}
    ]
    if unmarked:
        raise pytest.UsageError(
            "Tests need a marker (unit/integration/...): " + ", ".join(unmarked)
        )


@pytest.fixture
def results_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points the results store at a temporary directory."""
    monkeypatch.setattr(paths, "RESULTS_DIR", tmp_path / "results")
    return tmp_path / "results"


@pytest.fixture
def require_simulator() -> None:
    """Skips the test unless gem5 and the attack programs are built."""
    if not paths.GEM5_BIN.exists():
        pytest.skip("gem5 is not built; run tools/build")
    if not (paths.ATTACK_BIN_DIR / "dream_poc_sender").exists():
        pytest.skip("attack programs are not built; run tools/build --attacks")


def _flip(bits: str, count: int) -> str:
    """Returns "bits" with its first "count" bits inverted."""
    return "".join(
        ("1" if b == "0" else "0") if i < count else b
        for i, b in enumerate(bits)
    )


@pytest.fixture
def transmission_log() -> Callable[..., str]:
    """Returns a builder of a transmission simulation's log text."""

    def build(
        errors: int,
        msg_bits: int = 800,
        time_ns: int = 16019371,
        tag: str = "",
    ) -> str:
        """Builds a log whose receiver got exactly "errors" bits wrong."""
        sent = "01" * (msg_bits // 2)
        prefix = f"{tag}-" if tag else ""
        return "\n".join(
            [
                "Global frequency set at 1000000000000 ticks per second",
                f"[{prefix}SEND] Binary: {sent}",
                f"[{prefix}RECV] MinSleepAssert: 6715",
                f"[{prefix}RECV] Resyncs: 0 (0 bits skipped)",
                f"[{prefix}RECV] Received in {time_ns} ns",
                f"[{prefix}RECV] Binary: {_flip(sent, errors)}",
                "",
            ]
        )

    return build


@pytest.fixture
def poc_log() -> Callable[..., str]:
    """Returns a builder of a proof-of-concept log, per defense."""

    def build(
        defense: str,
        text: str = "MICRO",
        errors: int = 0,
        per_window: bool = True,
        binary: bool = True,
    ) -> str:
        """Builds a POC log in the defense's real format.

        "errors" is the number of bits the receiver got wrong. RFM and RRS
        print one "Received:" line per window ("per_window") and, in the
        real logs, also a final "Binary:" line ("binary").
        """
        sent = text_to_bits(text)
        received = _flip(sent, errors)
        if defense == "dream":
            counts = " ".join("2" if b == "1" else "0" for b in received)
            return "\n".join(
                [
                    f"[DREAM-POC-SEND] txn_period: 20000 message: '{text}'",
                    f"[DREAM-POC-SEND] Binary: {sent}",
                    f"[DREAM-POC-RECV] expected_msg: '{text}' (40 bits)",
                    "[DREAM-POC-RECV] Resyncs: 0 (0 bits skipped)",
                    f"[DREAM-POC-RECV] Binary: {received}",
                    f"[DREAM-POC-RECV] Spike counts: {counts} ",
                    f"[DREAM-POC-RECV] Decoded ASCII: "
                    f"'{bits_to_text(received)}'",
                    f"[DREAM-POC-RECV] Bit errors:  {errors} / 40  "
                    f"({errors / 40 * 100:.2f}%)",
                    "",
                ]
            )
        lines = [
            f"[SEND] Message: {text}",
            f"[SEND] Binary: {sent}",
            "[RECV] Resyncs: 0 (0 bits skipped)",
        ]
        if defense in ("rfm", "rrs") and per_window:
            unit = "RFMs" if defense == "rfm" else "SWAPs"
            lines += [
                f"[RECV] Received: {b} ({6 if b == '1' else 0} {unit})"
                for b in received
            ]
        if binary or defense == "prac":
            lines.append(f"[RECV] Binary: {received}")
        return "\n".join(lines) + "\n"

    return build


@pytest.fixture
def noise_csv() -> Callable[..., Path]:
    """Returns a writer of a noise-sweep CSV (the plot input)."""

    def write(
        path: Path,
        rates: Sequence[int],
        patterns: Sequence[str] = ("0x00", "0x55"),
        errors: int = 40,
    ) -> Path:
        """Writes one row per rate and pattern; returns the path."""
        sent = "01" * 400
        rows = [
            {
                "rate": rate,
                "pattern": pattern,
                "sent": sent,
                "received": _flip(sent, errors * (i + 1)),
                "time": 16019271,
                "errors": errors * (i + 1),
            }
            for i, rate in enumerate(rates)
            for pattern in patterns
        ]
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    return write


@pytest.fixture
def latency_log() -> Callable[..., str]:
    """Returns a builder of a latency-profile log."""

    def build(requests: int = 2000) -> str:
        """Builds a log with a "Dump Begin" section of per-request latencies."""
        dump = [f"{i}: Latency: {100 + (i % 7) * 50}" for i in range(requests)]
        return "\n".join(["Dump Begin", *dump, "Frontend:", ""])

    return build


@pytest.fixture
def tprac_trace_log() -> Callable[..., str]:
    """Returns a builder of the log a TPRAC run prints with "debug: true"."""

    def build(
        window_ns: int = 3900,
        window_clk: int = 6240,
        first_clk: int = 5680,
        count: int = 3,
        ranks: int = 2,
        recoveries: int = 0,
    ) -> str:
        """Builds the header, "count" rounds of one RFMab per rank, counters."""
        lines = [
            f"[TPRAC] window: {window_ns} ns = {window_clk} clk, "
            f"first RFM at clk {first_clk}"
        ]
        for k in range(count):
            clk = first_clk + k * window_clk
            lines += [f"[TPRAC] [{clk}] RFMab rank {r}" for r in range(ranks)]
        lines += [
            f"      prac_num_recovery: {recoveries}",
            f"      tprac_num_tb_rfm: {count * ranks}",
        ]
        return "\n".join([*lines, ""])

    return build


@pytest.fixture
def prac_debug_log() -> Callable[..., str]:
    """Returns a builder of the PRAC plugin's debug lines from events."""

    def build(events: Sequence[Sequence[object]]) -> str:
        """Builds lines from ("act"|"rfm", bank, row, count) tuples."""
        tags = {"act": "ACT", "rfm": "RFM"}
        return (
            "\n".join(
                f"[PRAC] [{bank}] [{tags[kind]}] Row: {row} Act: {count}"
                for kind, bank, row, count in events
            )
            + "\n"
        )

    return build


@pytest.fixture(scope="session")
def traced_poc() -> Callable[..., Path]:
    """Returns a runner of a defense's proof of concept with debug output."""

    def run(
        out_dir: Path,
        defense: str,
        plugins: Mapping[str, Mapping[str, Any]],
        timing: Optional[Mapping[str, int]] = None,
    ) -> Path:
        """Runs the proof of concept and returns its log path.

        - plugins: parameters to set on each controller plugin, by its "impl"
          (the tracked configs have no "debug" parameter, and should not).
        - timing: DRAM timings, in clocks, to override.

        Skips when the simulator or the defense's programs are not built.
        """
        spec = get_defense(defense)
        if not paths.GEM5_BIN.exists():
            pytest.skip("gem5 is not built; run tools/build")
        if not spec.poc_sender.exists():
            pytest.skip("attack programs are not built; run tools/build")
        config = yaml.safe_load(spec.config_path.read_text(encoding="utf-8"))
        controller = config["MemorySystem"]["BHDRAMController"]
        for entry in controller["plugins"]:
            plugin = entry["ControllerPlugin"]
            plugin.update(plugins.get(plugin["impl"], {}))
        if timing:
            config["MemorySystem"]["DRAM"].setdefault("timing", {}).update(
                timing
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        path = (out_dir / "ramulator.yaml").resolve()
        path.write_text(yaml.safe_dump(config, sort_keys=False), "utf-8")
        simulation = sim.poc(spec, out_dir.resolve())
        flag = "--ramulator-config="
        command = [
            f"{flag}{path}" if a.startswith(flag) else a
            for a in simulation.command
        ]
        return dataclasses.replace(simulation, command=command).run()

    return run


@pytest.fixture
def prac_abo_log() -> Callable[..., str]:
    """Returns a builder of the PRAC plugin's back-off debug lines."""

    def build(
        trigger: int = 128,
        start_clk: int = 1000,
        window_acts: int = 0,
        mitigations: int = 4,
        delay_acts: int = 4,
        recovery_clks: int = 1682,
        cut: bool = False,
    ) -> str:
        """Builds one back-off, in the order the plugin prints it.

        The plugin changes state before it counts the command that caused
        the change, so the last RFM of the recovery and the last activation
        of the delay are printed after their transitions.
        """

        def act(count: int) -> str:
            """Returns an activation line."""
            return f"[PRAC] [3] [ACT] Row: 9 Act: {count}"

        def move(clk: int, before: str, after: str) -> str:
            """Returns a state transition line."""
            return f"[PRAC] [{clk}] <ABOState::{before}> -> <ABOState::{after}>"

        lines = [
            act(trigger),
            f"[PRAC] [{start_clk}] <ABOState::NORMAL> Asserting ALERT_N.",
            move(start_clk, "NORMAL", "PRE_RECOVERY"),
            *[act(1)] * window_acts,
            move(start_clk + 288, "PRE_RECOVERY", "RECOVERY"),
        ]
        recovery_end = start_clk + 288 + recovery_clks
        lines.append(move(recovery_end, "RECOVERY", "DELAY"))
        lines += [
            f"[PRAC] [{b}] [RFM] Row: 9 Act: {trigger}"
            for b in range(mitigations)
        ]
        if cut:
            return "\n".join(lines) + "\n"
        lines += [act(1)] * (delay_acts - 1)
        lines.append(move(recovery_end + 5000, "DELAY", "NORMAL"))
        lines.append(act(1))
        return "\n".join(lines) + "\n"

    return build
