"""The proof-of-concept experiment."""

import shutil
from pathlib import Path
from typing import Any

import pytest

from leakyhammer import results, sim
from leakyhammer.defenses import get_defense
from leakyhammer.experiments.poc import main as poc
from leakyhammer.experiments.poc import run as poc_run


@pytest.mark.unit
def test_run_poc_decodes_and_stores_record(
    results_root: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DREAM POC log decodes to the report's 'd??&L' with 18/40 errors."""

    def fake_run(self: sim.Simulation, timeout: Any = None) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(data / "dream_poc.log", self.log_path)
        return self.log_path

    monkeypatch.setattr(sim.Simulation, "run", fake_run)
    batch = results.batch_dir("poc", "t")
    record = poc.run_poc(get_defense("dream"), batch, {"threshold": 62})
    assert record["status"] == "ok"
    assert (record["sent_text"], record["decoded_text"]) == ("UTECE", "d??&L")
    assert record["errors"] == 18
    assert record["trial"] == "dream_threshold62"
    assert results.load_record(batch / "dream_threshold62") == record


@pytest.mark.unit
def test_run_poc_records_failure_for_undecodable_log(
    results_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that printed nothing usable is a failed record, not a crash."""

    def fake_run(self: sim.Simulation, timeout: Any = None) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("segfault\n")
        return self.log_path

    monkeypatch.setattr(sim.Simulation, "run", fake_run)
    record = poc.run_poc(get_defense("rfm"), results.batch_dir("poc", "t"))
    assert record["status"] == "failed"
    assert "no sent/received bits" in record["error"]


@pytest.mark.unit
def test_parse_overrides_reads_yaml_scalars() -> None:
    """--set values become ints/strings as YAML would read them."""
    assert poc_run.parse_overrides(["threshold=62", "grouping=random"]) == {
        "threshold": 62,
        "grouping": "random",
    }
    with pytest.raises(ValueError, match="key=value"):
        poc_run.parse_overrides(["oops"])
