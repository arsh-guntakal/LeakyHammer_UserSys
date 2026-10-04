"""The noise-sweep experiment: config, trials, execution, and reporting."""

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest

from leakyhammer import results, sim
from leakyhammer.experiments.noise_sweep import main as ns
from leakyhammer.experiments.noise_sweep import plot as nsplot
from leakyhammer.experiments.noise_sweep import run as nsrun


def _write(tmp_path: Path, text: str) -> Path:
    """Writes a config file and returns its path."""
    path = tmp_path / "c.yaml"
    path.write_text(text)
    return path


@pytest.fixture
def fake_gem5(
    transmission_log: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> Dict[str, int]:
    """Replaces gem5 with a canned log (382 errors); counts invocations."""
    calls = {"n": 0}

    def fake_run(
        self: sim.Simulation,
        timeout: Optional[float] = None,
    ) -> Path:
        calls["n"] += 1
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(transmission_log(errors=382))
        return self.log_path

    monkeypatch.setattr(sim.Simulation, "run", fake_run)
    return calls


@pytest.mark.unit
def test_default_config_is_the_reports_68_trial_matrix() -> None:
    """The default config expands to the 68 simulations of the full matrix."""
    trials = ns.trials(ns.load_config("default"))
    assert len(trials) == 68
    assert len({t.id for t in trials}) == 68, "trial ids must be unique"
    assert sum(t.noise_rate is None for t in trials) == 16


@pytest.mark.unit
def test_trial_ids_encode_overrides_and_rate() -> None:
    """Ids distinguish variants (threshold) and baseline from noise runs."""
    config = ns.load_config("dream_threshold")
    ids = {t.id for t in ns.trials(config)}
    assert "dream_threshold62_p0x55_r0" in ids
    assert "dream_threshold500_p0xFF_r325" in ids
    assert len(ns.trials(config)) == 80


@pytest.mark.unit
def test_config_rejects_bad_input(tmp_path: Path) -> None:
    """Unknown keys/defenses and bad overrides fail with clear errors."""
    with pytest.raises(ValueError, match="unknown key"):
        ns.load_config(_write(tmp_path, "variants: [{defense: rfm}]\nbogus: 1"))
    with pytest.raises(ValueError, match="Unknown defense"):
        ns.load_config(_write(tmp_path, "variants: [{defense: nope}]"))
    with pytest.raises(ValueError, match="takes no overrides"):
        ns.load_config(
            _write(tmp_path, "variants: [{defense: prac, overrides: {a: 1}}]")
        )
    with pytest.raises(ValueError, match="duplicate"):
        ns.load_config(
            _write(tmp_path, "variants: [{defense: rfm}, {defense: rfm}]")
        )
    with pytest.raises(FileNotFoundError):
        ns.load_config("does_not_exist")


@pytest.mark.unit
def test_per_variant_noise_rates_override_the_defaults(tmp_path: Path) -> None:
    """A variant's own noise_rates replace the defense's default rates."""
    config = ns.load_config(
        _write(
            tmp_path,
            "patterns: ['0x00']\nvariants: [{defense: rfm, noise_rates: [7]}]",
        )
    )
    assert [t.noise_rate for t in ns.trials(config)] == [None, 7]


@pytest.mark.unit
def test_baseline_and_noise_can_be_selected(tmp_path: Path) -> None:
    """ "noise: false" yields baseline only, so quick checks stay quick."""
    config = ns.load_config(
        _write(
            tmp_path,
            "noise: false\npatterns: ['0x00']\nvariants: [{defense: rfm}]",
        )
    )
    assert [t.noise_rate for t in ns.trials(config)] == [None]


@pytest.mark.unit
def test_run_trial_records_result_and_skips_when_done(
    results_root: Path, fake_gem5: Dict[str, int]
) -> None:
    """A finished trial is stored once; re-running skips it unless forced."""
    trial = ns.trials(ns.load_config("quick"))[-1]
    batch = results.batch_dir("noise_sweep", "t")
    record = ns.run_trial(trial, batch)
    assert record["status"] == "ok"
    assert (record["errors"], record["txn_time_ns"]) == (382, 16019371)
    assert record["params"]["defense"] == trial.variant.defense
    assert set(record["provenance"]) == {
        "git",
        "config_sha256",
        "programs_sha256",
    }
    assert fake_gem5["n"] == 1

    ns.run_trial(trial, batch)
    assert fake_gem5["n"] == 1, "finished trial must not be re-run"
    ns.run_trial(trial, batch, force=True)
    assert fake_gem5["n"] == 2


@pytest.mark.unit
@pytest.mark.regression
def test_crashed_simulation_is_recorded_not_raised(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gem5 crash becomes a failed record so a sweep keeps going.

    Regression test: crashed runs used to leave logs that parsed as -1 errors
    and silently poisoned the averages.
    """

    def crash(self: sim.Simulation, timeout: Optional[float] = None) -> Path:
        raise RuntimeError("gem5 exited with status 139")

    monkeypatch.setattr(sim.Simulation, "run", crash)
    trial = ns.trials(ns.load_config("quick"))[0]
    batch = results.batch_dir("noise_sweep", "t")
    record = ns.run_trial(trial, batch)
    assert record["status"] == "failed"
    assert "status 139" in record["error"]
    assert not results.is_done(batch / trial.id)


@pytest.mark.unit
def test_single_trial_command_line(
    results_root: Path,
    fake_gem5: Dict[str, int],
    capsys: pytest.CaptureFixture,
) -> None:
    """main.py runs exactly one trial and reports its outcome."""
    status = ns.main(
        ["--defense", "dream", "--pattern", "0x55", "--noise-rate", "263"]
    )
    assert status == 0 and fake_gem5["n"] == 1
    assert "errors 382/800" in capsys.readouterr().out
    assert (results_root / "noise_sweep" / "single").is_dir()


@pytest.mark.unit
@pytest.mark.parametrize("module", [nsrun, nsplot])
def test_sweep_and_plot_require_a_config(module: Any) -> None:
    """run.py and plot.py refuse to start without --config."""
    with pytest.raises(SystemExit):
        module.main([])


@pytest.mark.unit
def test_report_aggregates_and_flags_missing(
    results_root: Path, fake_gem5: Dict[str, int], tmp_path: Path
) -> None:
    """The table summarizes finished trials and says what is missing."""
    config = ns.load_config(
        _write(
            tmp_path,
            "patterns: ['0x55']\nnoise: false\nvariants: [{defense: dream}]",
        )
    )
    batch = results.batch_dir("noise_sweep", "t")
    for trial in ns.trials(config):
        ns.run_trial(trial, batch)
    lines = nsplot.report(config, batch)
    assert "baseline" in lines[1] and "dream" in lines[1]
    assert "0.4775" in lines[1]  # 382 errors / 800 bits
    shutil.rmtree(batch / ns.trials(config)[0].id)
    assert "missing 1 trials" in "\n".join(nsplot.report(config, batch))


@pytest.mark.unit
def test_frame_has_the_columns_the_figures_read(
    results_root: Path, fake_gem5: Dict[str, int]
) -> None:
    """The per-defense CSV keeps its column order and values."""
    trial = ns.trials(ns.load_config("quick"))[-1]
    record = ns.run_trial(trial, results.batch_dir("noise_sweep", "t"))
    frame = nsplot.frame([record])
    assert list(frame.columns) == nsplot.CSV_COLUMNS
    assert frame.iloc[0]["errors"] == 382


@pytest.mark.unit
@pytest.mark.parametrize(
    ("defense", "rates", "knee"),
    [
        ("prac", (275, 475, 1075, 1975), 88),
        ("rfm", (200, 263, 325), 50),
        ("rrs", (200, 263, 325), 50),
        ("dream", (200, 263, 325), 50),
    ],
)
def test_capacity_figure_for_every_defense_style(
    defense: str,
    rates: tuple,
    knee: int,
    tmp_path: Path,
    noise_csv: Callable[..., Path],
) -> None:
    """One function draws every defense's figure and reports its knee point."""
    out = tmp_path / "f.pdf"
    numbers = nsplot.plot_capacity(
        noise_csv(tmp_path / "n.csv", rates), out, 100, defense
    )
    assert out.stat().st_size > 1000
    assert set(numbers) == {"capacity_at_knee", "capacity_lowest"}


@pytest.mark.unit
def test_capacity_figure_rejects_unknown_defense(
    tmp_path: Path, noise_csv: Callable[..., Path]
) -> None:
    """A defense without a figure style raises instead of guessing."""
    with pytest.raises(KeyError):
        nsplot.plot_capacity(
            noise_csv(tmp_path / "n.csv", (200, 263, 325)),
            tmp_path / "f.pdf",
            100,
            "nope",
        )


@pytest.mark.experiment
@pytest.mark.slow
def test_one_real_trial_end_to_end(
    results_root: Path, require_simulator: None, tmp_path: Path
) -> None:
    """A real 5-byte RFM trial runs through gem5 and is stored and plotted.

    Uses a short message so the simulation takes seconds, not minutes.
    """
    config = ns.load_config(
        _write(
            tmp_path,
            "patterns: ['0x00']\nmsg_bytes: 5\nnoise: false\n"
            "variants: [{defense: rfm}]",
        )
    )
    batch = results.batch_dir("noise_sweep", "e2e")
    (trial,) = ns.trials(config)
    record = ns.run_trial(trial, batch)
    assert record["status"] == "ok", record["error"]
    assert len(record["sent"]) == 40
    assert record["resyncs"] == 0
    assert nsplot.report(config, batch)[1].startswith("rfm")
