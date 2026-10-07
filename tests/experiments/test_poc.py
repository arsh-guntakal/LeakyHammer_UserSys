"""The proof-of-concept experiment."""

from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from leakyhammer import results, sim
from leakyhammer.defenses import Variant, parse_variant
from leakyhammer.experiments.poc import main as poc
from leakyhammer.experiments.poc import plot as pocplot
from leakyhammer.experiments.poc import run as pocrun


def _fake_run(text: str) -> Callable[..., Path]:
    """Returns a stand-in for "Simulation.run" that writes "text"."""

    def fake_run(self: sim.Simulation, timeout: Optional[float] = None) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(text)
        return self.log_path

    return fake_run


@pytest.mark.unit
def test_default_config_lists_every_defense() -> None:
    """The default config runs all four defenses."""
    config = poc.load_config("default")
    assert [v.defense for v in config.variants] == [
        "prac",
        "rfm",
        "dream",
        "rrs",
    ]


@pytest.mark.unit
def test_config_rejects_bad_input(tmp_path: Path) -> None:
    """Empty, duplicate and misspelled configs fail clearly."""
    path = tmp_path / "c.yaml"
    path.write_text("variants: []")
    with pytest.raises(ValueError, match="at least one"):
        poc.load_config(path)
    path.write_text("variants: [{defense: rfm}, {defense: rfm}]")
    with pytest.raises(ValueError, match="duplicate"):
        poc.load_config(path)


@pytest.mark.unit
def test_run_poc_decodes_and_stores_record(
    results_root: Path,
    poc_log: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DREAM POC log decodes to its text with the right error count."""
    monkeypatch.setattr(
        sim.Simulation, "run", _fake_run(poc_log("dream", "UTECE", errors=18))
    )
    batch = results.batch_dir("poc", "t")
    variant = parse_variant(
        {"defense": "dream", "overrides": {"threshold": 62}}
    )
    record = poc.run_poc(variant, batch)
    assert record["status"] == "ok"
    assert record["sent_text"] == "UTECE"
    assert record["errors"] == 18
    assert record["trial"] == "dream_threshold62"
    assert results.load_record(batch / "dream_threshold62") == record


@pytest.mark.unit
def test_run_poc_records_failure_for_undecodable_log(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that printed nothing usable is a failed record, not a crash."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run("segfault\n"))
    record = poc.run_poc(Variant("rfm"), results.batch_dir("poc", "t"))
    assert record["status"] == "failed"
    assert "no sent/received bits" in record["error"]


@pytest.mark.unit
def test_single_poc_command_line(
    results_root: Path,
    poc_log: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """main.py runs one defense's POC and prints the decoded message."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run(poc_log("rfm")))
    assert poc.main(["--defense", "rfm"]) == 0
    assert "decoded 'MICRO'" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("module", [pocrun, pocplot])
def test_run_and_plot_require_a_config(module: Any) -> None:
    """run.py and plot.py refuse to start without --config."""
    with pytest.raises(SystemExit):
        module.main([])


@pytest.mark.unit
@pytest.mark.parametrize("defense", ["prac", "rfm", "rrs", "dream"])
def test_every_defense_gets_a_figure(
    defense: str, tmp_path: Path, poc_log: Callable[..., str]
) -> None:
    """Each defense's POC log is turned into a non-empty figure."""
    log = tmp_path / "sim.log"
    text = "UTECE" if defense == "dream" else "MICRO"
    log.write_text(poc_log(defense, text, errors=4))
    out = tmp_path / "f.pdf"
    pocplot.plot_poc(defense, log, out)
    assert out.stat().st_size > 1000


@pytest.mark.unit
def test_plot_rejects_a_defense_without_a_figure(tmp_path: Path) -> None:
    """Asking for an unknown defense's figure raises ValueError."""
    with pytest.raises(ValueError, match="No proof-of-concept figure"):
        pocplot.plot_poc("nope", tmp_path / "a", tmp_path / "b")


@pytest.mark.unit
@pytest.mark.regression
def test_poc_plot_survives_non_utf8_bytes_in_log(
    tmp_path: Path, poc_log: Callable[..., str]
) -> None:
    """A log with raw non-UTF-8 bytes still plots.

    Regression test: the RRS receiver prints decoded characters raw, so logs
    can contain bytes like 0x82, which crashed the plotter's strict decode.
    """
    log = tmp_path / "rrs.log"
    log.write_bytes(poc_log("rrs", errors=16).encode() + b"\n\x82\x04\n")
    out = tmp_path / "f.pdf"
    pocplot.plot_poc("rrs", log, out)
    assert out.stat().st_size > 1000


@pytest.mark.unit
def test_plot_command_line_draws_next_to_each_log(
    results_root: Path,
    poc_log: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plot.py reads the same config as run.py and writes figure.pdf."""
    monkeypatch.setattr(sim.Simulation, "run", _fake_run(poc_log("prac")))
    batch = results.batch_dir("poc", "default")
    poc.run_poc(Variant("prac"), batch)
    assert pocplot.main(["--config", "default"]) == 1  # others not run yet
    assert (batch / "prac" / "figure.pdf").stat().st_size > 1000


@pytest.mark.experiment
@pytest.mark.slow
def test_dream_poc_experiment_end_to_end(
    results_root: Path, require_simulator: None
) -> None:
    """The DREAM POC experiment decodes 'UTECE' as 'd??&L' (18/40) in gem5.

    The simulation is deterministic, so this exact result guards the whole
    stack: plugin, attack programs, address mapping, and harness.
    """
    record = poc.run_poc(Variant("dream"), results.batch_dir("poc", "e2e"))
    assert record["status"] == "ok", record["error"]
    assert record["decoded_text"] == "d??&L"
    assert (record["errors"], record["resyncs"]) == (18, 0)
