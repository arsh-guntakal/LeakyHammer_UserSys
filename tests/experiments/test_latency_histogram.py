"""The latency-histogram experiment."""

from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from leakyhammer import paths, results, sim
from leakyhammer.experiments.latency_histogram import main as hist
from leakyhammer.experiments.latency_histogram import plot as histplot
from leakyhammer.experiments.latency_histogram import run as histrun

_SLOW = (0, 0, 0, 0, 3, 2, 1, 1, 0, 0)


def _fake_run(log_text: str) -> Callable[..., Path]:
    """Returns a stand-in for "Simulation.run" that writes "log_text"."""

    def run(self: sim.Simulation, timeout: Optional[float] = None) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(log_text)
        return self.log_path

    return run


@pytest.mark.unit
def test_default_config_has_a_positive_control() -> None:
    """The shipped config measures RFM, whose stall must be visible."""
    names = [v.name for v in hist.load_config("default").variants]
    assert "rfm_control" in names and len(set(names)) == len(names)


@pytest.mark.unit
def test_variants_of_one_defense_need_distinct_tags(tmp_path: Path) -> None:
    """Two untagged variants would overwrite each other's results."""
    path = tmp_path / "c.yaml"
    path.write_text("variants: [{defense: rrs}, {defense: rrs}]")
    with pytest.raises(ValueError, match="duplicate"):
        hist.load_config(path)


@pytest.mark.unit
def test_log_is_parsed_per_bit(
    histogram_log: Callable[..., str], tmp_path: Path
) -> None:
    """Mean probes per bin are averaged over the windows of each sent bit."""
    path = tmp_path / "sim.log"
    path.write_text(histogram_log(ones=_SLOW))
    log = hist.parse_histogram_log(path)
    assert len(log.windows) == 4 and log.late_ns is None
    assert hist.mean_probes(log, 1) == [float(c) for c in _SLOW]
    assert hist.mean_probes(log, 0)[0] == 5.0


@pytest.mark.unit
def test_log_without_histogram_lines_is_rejected(tmp_path: Path) -> None:
    """A receiver that crashed before printing is an error, not zeros."""
    path = tmp_path / "sim.log"
    path.write_text("Segmentation fault\n")
    with pytest.raises(ValueError, match="no histogram"):
        hist.parse_histogram_log(path)


@pytest.mark.unit
def test_a_visible_defense_shows_extra_slow_probes(
    results_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    histogram_log: Callable[..., str],
) -> None:
    """Slow probes only in windows of 1 give a positive tail difference."""
    monkeypatch.setattr(
        sim.Simulation, "run", _fake_run(histogram_log(ones=_SLOW))
    )
    variant = hist.load_config("default").variants[0]
    record = hist.run_trial(
        variant, results.batch_dir("latency_histogram", "t"), "0x55", 2
    )
    assert record["status"] == "ok"
    assert histplot.tail_difference(record, 250) == pytest.approx(7.0)


@pytest.mark.unit
def test_an_invisible_defense_shows_no_difference(
    results_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    histogram_log: Callable[..., str],
) -> None:
    """Identical histograms for 1 and 0 give a tail difference of zero."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run(histogram_log()))
    variant = hist.load_config("default").variants[0]
    record = hist.run_trial(
        variant, results.batch_dir("latency_histogram", "t"), "0x55", 2
    )
    assert histplot.tail_difference(record, 250) == 0.0


@pytest.mark.regression
@pytest.mark.unit
def test_a_late_receiver_is_a_failed_trial(
    results_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    histogram_log: Callable[..., str],
) -> None:
    """A receiver that missed the sender's start is recorded as failed.

    Its windows are shifted against the sender's, which looks exactly like "the
    defense is invisible" and was how a DREAM-C channel was first judged closed.
    """
    monkeypatch.setattr(
        sim.Simulation, "run", _fake_run(histogram_log(late_ns=600000))
    )
    variant = hist.load_config("default").variants[0]
    record = hist.run_trial(
        variant, results.batch_dir("latency_histogram", "t"), "0x55", 2
    )
    assert record["status"] == "failed" and "600000 ns late" in record["error"]


@pytest.mark.unit
def test_figure_is_drawn(
    results_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    histogram_log: Callable[..., str],
    tmp_path: Path,
) -> None:
    """A finished trial becomes a non-empty figure."""
    monkeypatch.setattr(
        sim.Simulation, "run", _fake_run(histogram_log(ones=_SLOW))
    )
    variant = hist.load_config("default").variants[0]
    record = hist.run_trial(
        variant, results.batch_dir("latency_histogram", "t"), "0x55", 2
    )
    out = tmp_path / "f.pdf"
    histplot.plot_histograms(
        {variant.name: record}, {variant.name: variant.label}, str(out)
    )
    assert out.stat().st_size > 1000


@pytest.mark.unit
@pytest.mark.parametrize("module", [histrun, histplot])
def test_run_and_plot_require_a_config(module: Any) -> None:
    """run.py and plot.py refuse to start without --config."""
    with pytest.raises(SystemExit):
        module.main([])


@pytest.mark.experiment
@pytest.mark.slow
def test_rfm_positive_control_end_to_end(
    results_root: Path, require_simulator: None
) -> None:
    """Under gem5, the RFM sender's stalls are visible to the receiver."""
    if not (paths.ATTACK_BIN_DIR / "latency_histogram").exists():
        pytest.skip("latency_histogram is not built")
    variant = hist.load_config("default").variants[0]
    record = hist.run_trial(
        variant, results.batch_dir("latency_histogram", "e2e"), "0x55", 4
    )
    assert record["status"] == "ok", record["error"]
    assert histplot.tail_difference(record, 250) > 0
