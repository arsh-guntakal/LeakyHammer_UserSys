"""The noise-sweep experiment: config, trials, execution, and reporting."""

import shutil
from pathlib import Path
from typing import Any, Dict

import pytest

from leakyhammer import results, sim
from leakyhammer.experiments.noise_sweep import config as cfg
from leakyhammer.experiments.noise_sweep import main as nsmain
from leakyhammer.experiments.noise_sweep import plot as nsplot


def _write(tmp_path: Path, text: str) -> Path:
    """Writes a config file and returns its path."""
    path = tmp_path / "c.yaml"
    path.write_text(text)
    return path


@pytest.fixture
def fake_gem5(data: Path, monkeypatch: pytest.MonkeyPatch) -> Dict[str, int]:
    """Replaces gem5 with a copy of a known-good log; counts invocations."""
    calls = {"n": 0}

    def fake_run(self: sim.Simulation, timeout: Any = None) -> Path:
        calls["n"] += 1
        self.out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(data / "dream_baseline_0x55.log", self.log_path)
        return self.log_path

    monkeypatch.setattr(sim.Simulation, "run", fake_run)
    return calls


@pytest.mark.unit
def test_default_config_is_the_reports_68_trial_matrix() -> None:
    """The default config expands to the 68 simulations of the full matrix."""
    trials = nsmain.trials(cfg.load_config("default"))
    assert len(trials) == 68
    assert len({t.id for t in trials}) == 68, "trial ids must be unique"
    assert sum(t.noise_rate is None for t in trials) == 16


@pytest.mark.unit
def test_trial_ids_encode_overrides_and_rate() -> None:
    """Ids distinguish variants (threshold) and baseline from noise runs."""
    config = cfg.load_config("dream_threshold")
    ids = {t.id for t in nsmain.trials(config)}
    assert "dream_threshold62_p0x55_r0" in ids
    assert "dream_threshold500_p0xFF_r325" in ids
    assert len(nsmain.trials(config)) == 80


@pytest.mark.unit
def test_config_rejects_bad_input(tmp_path: Path) -> None:
    """Unknown keys/defenses and bad overrides fail with clear errors."""
    with pytest.raises(ValueError, match="unknown key"):
        cfg.load_config(
            _write(tmp_path, "variants: [{defense: rfm}]\nbogus: 1")
        )
    with pytest.raises(ValueError, match="Unknown defense"):
        cfg.load_config(_write(tmp_path, "variants: [{defense: nope}]"))
    with pytest.raises(ValueError, match="takes no overrides"):
        cfg.load_config(
            _write(tmp_path, "variants: [{defense: prac, overrides: {a: 1}}]")
        )
    with pytest.raises(ValueError, match="duplicate"):
        cfg.load_config(
            _write(tmp_path, "variants: [{defense: rfm}, {defense: rfm}]")
        )
    with pytest.raises(FileNotFoundError):
        cfg.load_config("does_not_exist")


@pytest.mark.unit
def test_baseline_and_noise_can_be_selected(tmp_path: Path) -> None:
    """ "noise: false" yields baseline only, so quick checks stay quick."""
    config = cfg.load_config(
        _write(
            tmp_path,
            "noise: false\npatterns: ['0x00']\nvariants: [{defense: rfm}]",
        )
    )
    trials = nsmain.trials(config)
    assert [t.noise_rate for t in trials] == [None]


@pytest.mark.unit
def test_run_trial_records_result_and_skips_when_done(
    results_root: Path, fake_gem5: Dict[str, int]
) -> None:
    """A finished trial is stored once; re-running skips it unless forced."""
    trial = nsmain.trials(cfg.load_config("quick"))[-1]
    batch = results.batch_dir("noise_sweep", "t")
    record = nsmain.run_trial(trial, batch)
    assert record["status"] == "ok"
    assert (record["errors"], record["txn_time_ns"]) == (382, 16019371)
    assert record["params"]["defense"] == trial.variant.defense
    assert set(record["provenance"]) == {
        "git",
        "config_sha256",
        "programs_sha256",
    }
    assert fake_gem5["n"] == 1

    nsmain.run_trial(trial, batch)
    assert fake_gem5["n"] == 1, "finished trial must not be re-run"
    nsmain.run_trial(trial, batch, force=True)
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

    def crash(self: sim.Simulation, timeout: Any = None) -> Path:
        raise RuntimeError("gem5 exited with status 139")

    monkeypatch.setattr(sim.Simulation, "run", crash)
    trial = nsmain.trials(cfg.load_config("quick"))[0]
    batch = results.batch_dir("noise_sweep", "t")
    record = nsmain.run_trial(trial, batch)
    assert record["status"] == "failed"
    assert "status 139" in record["error"]
    assert not results.is_done(batch / trial.id)


@pytest.mark.unit
def test_report_aggregates_and_flags_missing(
    results_root: Path, fake_gem5: Dict[str, int], tmp_path: Path
) -> None:
    """The table summarizes finished trials and says what is missing."""
    config = cfg.load_config(
        _write(
            tmp_path,
            "patterns: ['0x55']\nnoise: false\nvariants: [{defense: dream}]",
        )
    )
    batch = results.batch_dir("noise_sweep", "t")
    for trial in nsmain.trials(config):
        nsmain.run_trial(trial, batch)
    lines = nsplot.report(config, batch)
    assert "baseline" in lines[1] and "dream" in lines[1]
    assert "0.4775" in lines[1]  # 382 errors / 800 bits
    # Remove the only trial: reported as missing, not crashed.
    shutil.rmtree(batch / nsmain.trials(config)[0].id)
    assert "missing 1 trials" in "\n".join(nsplot.report(config, batch))


@pytest.mark.unit
def test_frame_has_the_columns_the_plotters_read(
    results_root: Path, fake_gem5: Dict[str, int]
) -> None:
    """The per-defense CSV keeps the legacy column order and values."""
    trial = nsmain.trials(cfg.load_config("quick"))[-1]
    record = nsmain.run_trial(trial, results.batch_dir("noise_sweep", "t"))
    frame = nsplot.frame([record])
    assert list(frame.columns) == nsplot.CSV_COLUMNS
    assert frame.iloc[0]["errors"] == 382
