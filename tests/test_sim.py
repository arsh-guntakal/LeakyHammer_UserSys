"""Building gem5 commands and applying config overrides."""

import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from leakyhammer import paths, sim
from leakyhammer.defenses import get_defense


def _flag(command: List[str], prefix: str) -> str:
    """Returns the value of the "--prefix=" argument of a command."""
    (match,) = [a for a in command if a.startswith(prefix + "=")]
    return match.split("=", 1)[1]


@pytest.mark.unit
def test_baseline_transmission_command(tmp_path: Path) -> None:
    """A no-noise run uses two CPUs and sends the same args to both programs."""
    s = sim.transmission(get_defense("dream"), "0x55", 100, tmp_path)
    assert _flag(s.command, "--num-cpu") == "2"
    assert _flag(s.command, "--cmd") == "./dream_sender;./dream_receiver"
    assert _flag(s.command, "--options") == "20000 100 0x55;20000 100 0x55"
    assert _flag(s.command, "--mem-size") == "32GB"
    assert s.command[0] == str(paths.GEM5_BIN)


@pytest.mark.unit
@pytest.mark.regression
def test_guest_programs_do_not_depend_on_the_checkout_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The strings the guest sees are identical wherever the repo lives.

    Regression test: guest programs used to be started by absolute path, and
    that string is copied onto the simulated stack, where its length changes
    results (PRAC's baseline time shifted by 32 ns and RFM's 0xFF run by 28
    bit errors for a path one byte longer). Programs are now "./<name>", run
    from the binaries directory.
    """
    monkeypatch.delenv(sim.GUEST_BIN_DIR_ENV, raising=False)
    first = sim.transmission(get_defense("prac"), "0x00", 100, tmp_path, 475)
    monkeypatch.setattr(paths, "ATTACK_BIN_DIR", Path("/elsewhere/much/longer"))
    other = sim.transmission(get_defense("prac"), "0x00", 100, tmp_path, 475)
    assert _flag(first.command, "--cmd") == _flag(other.command, "--cmd")
    assert (
        _flag(first.command, "--cmd")
        == "./prac_sender;./prac_receiver;./mr_noise"
    )
    assert other.cwd == Path("/elsewhere/much/longer")


@pytest.mark.unit
def test_guest_dir_override_pins_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The override reproduces a measurement made at a specific path."""
    monkeypatch.setenv(sim.GUEST_BIN_DIR_ENV, "/app/attack-binaries/")
    s = sim.transmission(get_defense("rfm"), "0x00", 100, tmp_path)
    assert _flag(s.command, "--cmd") == (
        "/app/attack-binaries/rfm_sender;/app/attack-binaries/rfm_receiver"
    )
    assert s.cwd is None


@pytest.mark.unit
def test_noise_transmission_adds_generator_process(tmp_path: Path) -> None:
    """Noise adds a third CPU and process running 1.5x the message duration."""
    s = sim.transmission(get_defense("prac"), "0x00", 100, tmp_path, 475)
    assert _flag(s.command, "--num-cpu") == "3"
    assert _flag(s.command, "--cmd").endswith(";./mr_noise")
    # 25000 ns * 100 bytes * 8 bits * 1.5, written as the original did.
    assert _flag(s.command, "--options").endswith(";30000000.0 32 475")


@pytest.mark.unit
def test_each_simulation_writes_under_its_own_directory(tmp_path: Path) -> None:
    """gem5's output goes to the trial dir so parallel runs never collide."""
    s = sim.transmission(get_defense("rfm"), "0xFF", 100, tmp_path / "t")
    assert _flag(s.command, "--outdir") == str(tmp_path / "t" / "m5out")
    assert s.log_path == tmp_path / "t" / "sim.log"


@pytest.mark.unit
def test_overrides_write_a_modified_copy_and_leave_the_original(
    tmp_path: Path,
) -> None:
    """Overrides edit a per-trial copy of the config, never the tracked file."""
    dream = get_defense("dream")
    before = dream.config_path.read_text()
    s = sim.transmission(dream, "0x55", 100, tmp_path, None, {"threshold": 62})
    assert dream.config_path.read_text() == before
    assert _flag(s.command, "--ramulator-config") == str(
        tmp_path / "ramulator.yaml"
    )
    config = yaml.safe_load((tmp_path / "ramulator.yaml").read_text())
    plugin = config["MemorySystem"]["BHDRAMController"]["plugins"][0]
    assert plugin["ControllerPlugin"]["threshold"] == 62
    assert plugin["ControllerPlugin"]["impl"] == "DREAM"


@pytest.mark.unit
def test_overrides_reject_unknown_parameters(tmp_path: Path) -> None:
    """A misspelled plugin parameter fails loudly instead of being ignored."""
    with pytest.raises(ValueError, match="no parameter"):
        sim.effective_config(get_defense("dream"), tmp_path, {"treshold": 1})


@pytest.mark.unit
def test_overrides_reject_defense_without_plugin(tmp_path: Path) -> None:
    """Defenses with no tunable plugin refuse overrides."""
    with pytest.raises(ValueError, match="no tunable plugin"):
        sim.effective_config(get_defense("prac"), tmp_path, {"x": 1})


@pytest.mark.unit
def test_poc_uses_defense_specific_options(tmp_path: Path) -> None:
    """DREAM's POC passes its message text; PRAC uses its longer window."""
    assert _flag(
        sim.poc(get_defense("dream"), tmp_path).command, "--options"
    ) == ("20000 5 0x00 UTECE;20000 5 0x00 UTECE")
    assert _flag(
        sim.poc(get_defense("prac"), tmp_path).command, "--options"
    ) == ("25000 5 aa;25000 5 aa")


@pytest.mark.unit
def test_shell_command_quotes_paths(tmp_path: Path) -> None:
    """The one-line form survives spaces in paths and redirects the log."""
    s = sim.transmission(get_defense("rfm"), "0x00", 100, tmp_path / "a b")
    line = s.shell_command()
    assert "'" in line and line.endswith("2>&1")
    assert "sim.log" in line
    assert line.startswith(f"cd {paths.ATTACK_BIN_DIR} && ")


@pytest.mark.unit
def test_run_raises_on_nonzero_exit_and_keeps_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashed gem5 raises with the log path; the log is kept."""

    def fake_run(cmd: List[str], **kwargs: Any) -> Any:
        kwargs["stdout"].write("boom\n")
        return subprocess.CompletedProcess(cmd, 139)

    monkeypatch.setattr(subprocess, "run", fake_run)
    s = sim.transmission(get_defense("rfm"), "0x00", 100, tmp_path)
    with pytest.raises(RuntimeError, match="status 139"):
        s.run()
    assert s.log_path.read_text() == "boom\n"


@pytest.mark.unit
def test_run_hides_virtualenv_from_gem5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gem5 embeds the system Python, so venv variables must not leak in."""
    seen: Dict[str, Any] = {}

    def fake_run(cmd: List[str], **kwargs: Any) -> Any:
        seen.update(kwargs["env"])
        seen["__cwd__"] = kwargs["cwd"]
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    monkeypatch.setenv("PYTHONHOME", "/some/home")
    monkeypatch.setattr(subprocess, "run", fake_run)
    sim.transmission(get_defense("rfm"), "0x00", 100, tmp_path).run()
    assert "VIRTUAL_ENV" not in seen and "PYTHONHOME" not in seen
    assert seen["__cwd__"] == paths.ATTACK_BIN_DIR, "guest paths are relative"


@pytest.mark.unit
def test_guest_command_is_what_the_guest_is_started_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorded guest command follows the guest-directory override.

    Results depend on this string's length, so each result records it.
    """
    monkeypatch.delenv(sim.GUEST_BIN_DIR_ENV, raising=False)
    s = sim.transmission(get_defense("rfm"), "0x00", 100, tmp_path)
    assert s.guest_command == "./rfm_sender;./rfm_receiver"
    monkeypatch.setenv(sim.GUEST_BIN_DIR_ENV, "/x/y")
    s = sim.transmission(get_defense("rfm"), "0x00", 100, tmp_path)
    assert s.guest_command == "/x/y/rfm_sender;/x/y/rfm_receiver"
