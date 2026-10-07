"""The defense registry."""

import pytest

from leakyhammer import defenses, paths


@pytest.mark.unit
def test_every_defense_has_config_and_attack_sources() -> None:
    """Each defense ships a Ramulator config and all four programs."""
    for defense in defenses.DEFENSES.values():
        assert defense.config_path.is_file(), defense.config_path
        for role in defense.roles:
            source = defense.source_dir / f"{role}.cc"
            assert source.is_file(), source


@pytest.mark.unit
def test_get_defense_is_case_insensitive_and_strict() -> None:
    """Names resolve regardless of case; unknown names list the choices."""
    assert defenses.get_defense("DREAM").name == "dream"
    with pytest.raises(ValueError, match="choose from"):
        defenses.get_defense("nope")


@pytest.mark.unit
def test_program_paths_follow_naming_convention() -> None:
    """Compiled programs are "<defense>_<role>" in the attack binary dir."""
    dream = defenses.get_defense("dream")
    assert dream.sender == paths.ATTACK_BIN_DIR / "dream_sender"
    assert dream.poc_receiver == paths.ATTACK_BIN_DIR / "dream_poc_receiver"


@pytest.mark.unit
def test_prerevert_rfm_differs_from_rfm_only_in_timing() -> None:
    """The legacy RFM config is rfm.yaml plus five RFM/DRFM timing overrides.

    This is what makes it reproduce the pre-revert stalls without any
    Ramulator source change.
    """
    import yaml

    base = yaml.safe_load(defenses.get_defense("rfm").config_path.read_text())
    legacy = yaml.safe_load(
        defenses.get_defense("rfm_prerevert").config_path.read_text()
    )
    timing = legacy["MemorySystem"]["DRAM"]["timing"]
    assert {k: timing.pop(k) for k in list(timing) if k != "preset"} == {
        "nRFM1": 5000,
        "nRFM2": 5000,
        "nRFMsb": 5000,
        "nDRFMab": 5000,
        "nDRFMsb": 5000,
    }
    assert legacy == base


@pytest.mark.unit
def test_prerevert_rfm_has_no_proof_of_concept() -> None:
    """The legacy defense only has the programs the matrix needs."""
    assert defenses.get_defense("rfm_prerevert").roles == (
        "sender",
        "receiver",
    )
