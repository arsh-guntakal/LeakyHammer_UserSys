"""The defense registry."""

import pytest

from leakyhammer import defenses, paths
from leakyhammer.attacks import build


@pytest.mark.unit
def test_every_defense_has_config_and_attack_sources() -> None:
    """Each defense ships a Ramulator config and all four programs."""
    for defense in defenses.DEFENSES.values():
        assert defense.config_path.is_file(), defense.config_path
        for role in build.ROLES:
            source = paths.ATTACK_SRC_DIR / defense.name / f"{role}.cc"
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
