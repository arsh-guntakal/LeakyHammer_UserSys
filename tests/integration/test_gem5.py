"""Core library against a real simulator (needs tools/build first)."""

from pathlib import Path

import pytest

from leakyhammer import sim
from leakyhammer.defenses import get_defense
from leakyhammer.metrics import parse_poc


@pytest.mark.integration
@pytest.mark.slow
def test_dream_poc_is_deterministic(
    tmp_path: Path, require_simulator: None
) -> None:
    """DREAM's POC decodes to 'TTE??' (7/40 errors) every time.

    The simulation is deterministic, so this exact result is a regression
    guard for the whole stack: Ramulator plugin, attack programs, address
    mapping, and the harness.
    """
    log = sim.poc(get_defense("dream"), tmp_path).run()
    decoded = parse_poc(log)
    assert decoded.sent_text == "UTECE"
    assert decoded.decoded_text == "TTE??"
    assert (decoded.errors, decoded.resyncs) == (7, 0)


@pytest.mark.integration
@pytest.mark.slow
def test_rfm_poc_decodes_message(
    tmp_path: Path, require_simulator: None
) -> None:
    """RFM, the vulnerable baseline, transmits 'MICRO' with no errors."""
    decoded = parse_poc(sim.poc(get_defense("rfm"), tmp_path).run())
    assert (decoded.decoded_text, decoded.errors) == ("MICRO", 0)
