"""The latency-profile experiment."""

from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from leakyhammer import paths, results, sim
from leakyhammer.defenses import Variant
from leakyhammer.experiments.latency_profile import main as lat
from leakyhammer.experiments.latency_profile import plot as latplot
from leakyhammer.experiments.latency_profile import run as latrun


@pytest.mark.unit
def test_only_plain_prac_can_be_profiled(tmp_path: Path) -> None:
    """The figure's bands are PRAC's, so other defenses are refused."""
    assert [v.defense for v in lat.load_config("default").variants] == ["prac"]
    path = tmp_path / "c.yaml"
    path.write_text("variants: [{defense: rfm}]")
    with pytest.raises(ValueError, match="only plain 'prac'"):
        lat.load_config(path)


@pytest.mark.unit
def test_run_profile_records_success_and_failure(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished profile is recorded as ok; a crash as failed, not raised."""
    batch = results.batch_dir("latency_profile", "t")
    monkeypatch.setattr(
        sim.Simulation,
        "run",
        lambda self, timeout=None: self.out_dir.mkdir(
            parents=True, exist_ok=True
        ),
    )
    assert lat.run_profile(Variant("prac"), batch)["status"] == "ok"

    def crash(self: sim.Simulation, timeout: Optional[float] = None) -> Path:
        raise RuntimeError("gem5 exited with status 1")

    monkeypatch.setattr(sim.Simulation, "run", crash)
    failed = lat.run_profile(Variant("prac"), batch)
    assert failed["status"] == "failed" and "status 1" in failed["error"]


@pytest.mark.unit
def test_latencies_are_read_from_the_dump(
    tmp_path: Path, latency_log: Callable[..., str]
) -> None:
    """Only lines of the "Dump Begin" section are latencies."""
    log = tmp_path / "sim.log"
    log.write_text("1: Latency: 999\n" + latency_log(requests=10))
    latencies = latplot.parse_latencies(log)
    assert len(latencies) == 10 and 999 not in latencies


@pytest.mark.unit
def test_latency_figure_is_drawn(
    tmp_path: Path, latency_log: Callable[..., str]
) -> None:
    """A latency log becomes a non-empty figure."""
    log = tmp_path / "sim.log"
    log.write_text(latency_log())
    out = tmp_path / "f.pdf"
    latplot.plot_latency(log, out)
    assert out.stat().st_size > 1000


@pytest.mark.unit
@pytest.mark.parametrize("module", [latrun, latplot])
def test_run_and_plot_require_a_config(module: Any) -> None:
    """run.py and plot.py refuse to start without --config."""
    with pytest.raises(SystemExit):
        module.main([])


@pytest.mark.experiment
@pytest.mark.slow
def test_latency_profile_experiment_end_to_end(
    results_root: Path, require_simulator: None
) -> None:
    """A real profile runs under gem5 and its log yields many latencies."""
    if not (paths.ATTACK_BIN_DIR / "mr_latency").exists():
        pytest.skip("mr_latency is not built")
    batch = results.batch_dir("latency_profile", "e2e")
    assert lat.run_profile(Variant("prac"), batch)["status"] == "ok"
    assert len(latplot.parse_latencies(batch / "prac" / "sim.log")) > 1000
