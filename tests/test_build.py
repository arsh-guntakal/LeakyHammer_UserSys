"""Compiling the guest attack programs (command construction only)."""

import pytest

from leakyhammer import paths
from leakyhammer.attacks import build
from leakyhammer.defenses import DEFENSES


@pytest.mark.unit
def test_targets_cover_every_defense_role_plus_helpers() -> None:
    """Every defense yields four programs, plus the noise and latency tools."""
    names = set(build.targets())
    for defense in DEFENSES.values():
        assert {f"{defense.name}_{role}" for role in defense.roles} <= names
    assert {"mr_noise", "mr_latency", "latency_histogram"} <= names
    assert len(names) == sum(len(d.roles) for d in DEFENSES.values()) + 3


@pytest.mark.unit
def test_select_expands_defense_and_helper_names() -> None:
    """A defense name selects its four programs; "noise" the generator."""
    assert {t.name for t in build.select(["dream"])} == {
        f"dream_{r}" for r in build.ROLES
    }
    assert [t.name for t in build.select(["noise"])] == ["mr_noise"]
    assert len(build.select([])) == len(build.targets())


@pytest.mark.unit
def test_select_rejects_unknown_names() -> None:
    """Typos list the valid choices."""
    with pytest.raises(ValueError, match="Unknown target 'drem'"):
        build.select(["drem"])


@pytest.mark.unit
def test_compile_command_links_m5_and_shared_library() -> None:
    """Each program builds with the shared library, gem5 headers and libm5."""
    target = build.targets()["rrs_sender"]
    cmd = build.compile_command(target, cxx="g++")
    assert cmd[0] == "g++" and "-static" in cmd
    assert str(build.COMMON_DIR / "rowhammer-side.cc") in cmd
    assert str(paths.M5_LIB) == cmd[-1]
    assert str(paths.GEM5_INCLUDE_DIR) in cmd


@pytest.mark.unit
@pytest.mark.regression
def test_binaries_embed_the_original_artifacts_source_paths() -> None:
    """Embedded source paths equal the original artifact's, not ours.

    Regression test: the embedded paths set the length of strings in the
    binary's read-only data, which shifts constants across cache lines and
    changed measurements (RFM baseline 0x55: 109 bit errors, not 106). They
    must also not contain the checkout path.
    """
    cmd = build.compile_command(build.targets()["rfm_sender"])
    maps = [a for a in cmd if a.startswith("-ffile-prefix-map=")]
    assert f"-ffile-prefix-map={paths.REPO_ROOT}=." in maps
    assert maps[-1].endswith("=./attack-scripts/rowhammer-rfm-sender.cc")
    assert maps[-2].endswith("=./attack-scripts")  # rowhammer-side.cc/.hh


@pytest.mark.unit
def test_legacy_names_follow_the_original_artifacts_scheme() -> None:
    """Each program maps to the file name the original artifact used."""
    assert build.legacy_name("dream", "sender") == "rowhammer-dream-sender.cc"
    assert build.legacy_name("rrs", "poc_receiver") == "rrs-poc-receiver.cc"
    targets = build.targets()
    assert targets["mr_noise"].legacy_name == "rowhammer-mr-noise.cc"
    assert targets["mr_latency"].legacy_name == "rowhammer-mr-latency.cc"


@pytest.mark.unit
def test_noise_generator_builds_with_werror() -> None:
    """The noise generator keeps the strict -Werror build it always had."""
    assert "-Werror" in build.targets()["mr_noise"].flags
    assert "-Werror" not in build.targets()["dream_sender"].flags


@pytest.mark.unit
@pytest.mark.regression
def test_compiler_ignores_cxx_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attack programs build with plain g++ even when CXX names another.

    Regression test: the container exports CXX=g++-10, and honoring it built
    differently laid-out binaries than the original artifact's g++ 9.4, which
    shifted measured BERs (RFM baseline 0x55: 89 errors instead of 106).
    """
    monkeypatch.setenv("CXX", "g++-10")
    monkeypatch.delenv("LEAKYHAMMER_CXX", raising=False)
    target = build.targets()["rfm_sender"]
    assert build.compile_command(target)[0] == "g++"
    monkeypatch.setenv("LEAKYHAMMER_CXX", "clang++")
    assert build.compile_command(target)[0] == "clang++"


@pytest.mark.unit
def test_legacy_defense_builds_against_its_own_library() -> None:
    """The pre-revert RFM links its own copy of the shared sources.

    Its programs must see the old latency bands, so they cannot use
    "attacks/common", yet must embed the original artifact's file names.
    """
    target = build.targets()["rfm_prerevert_sender"]
    assert (
        target.common_dir == paths.ATTACK_SRC_DIR / "legacy" / "rfm_prerevert"
    )
    assert target.legacy_name == "rowhammer-rfm-sender.cc"
    cmd = build.compile_command(target, cxx="g++")
    assert str(target.common_dir / "rowhammer-side.cc") in cmd
    assert str(build.COMMON_DIR / "rowhammer-side.cc") not in cmd
    # The current RFM still uses the shared library.
    assert build.targets()["rfm_sender"].common_dir == build.COMMON_DIR
