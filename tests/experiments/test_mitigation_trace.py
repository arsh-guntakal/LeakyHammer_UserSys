"""The mitigation-trace experiment."""

from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from leakyhammer import results, sim
from leakyhammer.experiments.mitigation_trace import main as trace
from leakyhammer.experiments.mitigation_trace import plot as traceplot
from leakyhammer.experiments.mitigation_trace import run as tracerun


def _fake_run(log_text: str) -> Callable[..., Path]:
    """Returns a stand-in for "Simulation.run" that writes "log_text"."""

    def run(self: sim.Simulation, timeout: Optional[float] = None) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(log_text)
        return self.log_path

    return run


_HIT_LINE = (
    "[Ramulator::DREAM] T_TH hit: rank=1 bank_in_rank=0 row=0 dct_idx=0 "
    "clk=1 -> issuing 1 DRFMab\n"
)


@pytest.mark.unit
def test_hammering_windows_includes_the_fixed_preamble() -> None:
    """Even a message with no set bits still hammers the preamble's windows."""
    assert trace.hammering_windows("0x00", 100) == 8
    assert trace.hammering_windows("0xFF", 100) == 8 + 800
    assert trace.hammering_windows("0x55", 2) == 8 + 8


@pytest.mark.unit
def test_count_mitigations_counts_only_hit_lines(tmp_path: Path) -> None:
    """Other log lines are not mistaken for a mitigation."""
    log = tmp_path / "sim.log"
    log.write_text("[Ramulator::DREAM] config: threshold=40\n" + _HIT_LINE * 3)
    assert trace.count_mitigations(log) == 3


@pytest.mark.unit
def test_idle_message_still_mitigates_the_preamble(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A message with no set bits still hammers, and mitigates, the preamble."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run(_HIT_LINE * 2))
    batch = results.batch_dir("mitigation_trace", "t")
    record = trace.run_trial(40, "0x00", 10, batch)
    assert record["status"] == "ok"
    assert (record["mitigations"], record["hammering_windows"]) == (2, 8)


@pytest.mark.unit
def test_hammering_pattern_mitigates_more(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sender that sets every bit triggers more mitigations than idle."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run(_HIT_LINE * 40))
    batch = results.batch_dir("mitigation_trace", "t")
    record = trace.run_trial(40, "0xFF", 10, batch)
    assert record["status"] == "ok"
    assert record["mitigations"] == 40
    assert record["hammering_windows"] == 8 + 80


@pytest.mark.unit
def test_crashed_simulation_is_recorded_as_failed(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gem5 crash is stored with its error, not raised."""

    def crash(self: sim.Simulation, timeout: Optional[float] = None) -> Path:
        raise RuntimeError("gem5 exited with status 1")

    monkeypatch.setattr(sim.Simulation, "run", crash)
    batch = results.batch_dir("mitigation_trace", "t")
    record = trace.run_trial(40, "0xFF", 10, batch)
    assert record["status"] == "failed" and "status 1" in record["error"]


@pytest.mark.unit
def test_figure_is_drawn(
    results_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A batch of finished trials becomes a non-empty figure."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run(_HIT_LINE * 5))
    batch = results.batch_dir("mitigation_trace", "t")
    record = trace.run_trial(40, "0x55", 10, batch)
    out = tmp_path / "f.pdf"
    traceplot.plot_mitigations([record], str(out))
    assert out.stat().st_size > 1000


@pytest.mark.unit
@pytest.mark.parametrize("module", [tracerun, traceplot])
def test_run_and_plot_require_a_config(module: Any) -> None:
    """run.py and plot.py refuse to start without --config."""
    with pytest.raises(SystemExit):
        module.main([])


@pytest.mark.experiment
@pytest.mark.slow
def test_dream_mitigates_in_proportion_to_hammering_end_to_end(
    results_root: Path, require_simulator: None
) -> None:
    """Under gem5, DREAM-C mitigates more as the sender hammers more.

    This is the correctness claim behind every DREAM-C leakage result: the
    plugin's own tracker and threshold logic fire in proportion to genuine
    hammering (idle's few mitigations come only from the fixed calibration
    preamble every message hammers through), not spuriously or at some fixed
    rate regardless of input. So what the covert-channel experiments measure
    is the defense working as specified, not a quirk of the attack.
    """
    batch = results.batch_dir("mitigation_trace", "e2e")
    idle = trace.run_trial(40, "0x00", 10, batch)
    hammering = trace.run_trial(40, "0xFF", 10, batch)
    assert idle["status"] == "ok", idle["error"]
    assert hammering["status"] == "ok", hammering["error"]
    assert hammering["mitigations"] > idle["mitigations"] > 0
