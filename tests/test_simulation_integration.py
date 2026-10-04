"""End-to-end: run real gem5 simulations (needs the built simulator)."""

import pytest

from leakyhammer import paths, results
from leakyhammer.defenses import get_defense
from leakyhammer.experiments.poc import main as poc

needs_simulator = pytest.mark.skipif(
    not paths.GEM5_BIN.exists()
    or not (paths.ATTACK_BIN_DIR / "dream_poc_sender").exists(),
    reason="build first: tools/build",
)


@pytest.mark.integration
@pytest.mark.slow
@needs_simulator
def test_dream_poc_is_deterministic_and_closed(results_root: object) -> None:
    """DREAM's POC decodes to the report's 'd??&L' (18/40) every time.

    The simulation is deterministic, so this exact result is a regression
    guard for the whole stack: Ramulator plugin, attack binaries, address
    mapping, and the harness.
    """
    record = poc.run_poc(
        get_defense("dream"), results.batch_dir("poc", "integration")
    )
    assert record["status"] == "ok", record["error"]
    assert record["decoded_text"] == "d??&L"
    assert record["errors"] == 18
    assert record["resyncs"] == 0


@pytest.mark.integration
@pytest.mark.slow
@needs_simulator
def test_rfm_poc_decodes_message(results_root: object) -> None:
    """RFM, the vulnerable baseline, transmits 'MICRO' with no errors."""
    record = poc.run_poc(
        get_defense("rfm"), results.batch_dir("poc", "integration")
    )
    assert record["status"] == "ok", record["error"]
    assert (record["decoded_text"], record["errors"]) == ("MICRO", 0)
