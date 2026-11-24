"""PRAC's behavior: parsing its trace, then the plugin against a simulator."""

import concurrent.futures
import dataclasses
from pathlib import Path
from typing import Callable, Dict, Optional

import pytest

from leakyhammer import metrics


@pytest.mark.unit
def test_abo_trace_reads_one_back_off(
    tmp_path: Path, prac_abo_log: Callable[..., str]
) -> None:
    """A back-off parses to its trigger, phase clocks and the counts in each."""
    log = tmp_path / "sim.log"
    log.write_text(prac_abo_log(trigger=128, window_acts=2, mitigations=256))
    trace = metrics.parse_abo_trace(log)
    assert (len(trace.episodes), trace.incomplete) == (1, 0)
    (episode,) = trace.episodes
    assert episode.trigger_count == 128
    assert episode.recovery_clk - episode.assert_clk == 288
    assert episode.delay_clk - episode.recovery_clk == 1682
    assert episode.window_acts == 2
    assert episode.recovery_mitigations == 256
    assert episode.recovery_max_count == 128
    # The closing activation is logged after the transition that it causes.
    assert episode.delay_acts == 4


@pytest.mark.unit
def test_abo_trace_counts_a_cut_off_back_off_as_incomplete(
    tmp_path: Path, prac_abo_log: Callable[..., str]
) -> None:
    """A run that ends inside the delay does not yield a half-read episode."""
    log = tmp_path / "sim.log"
    log.write_text(prac_abo_log() + prac_abo_log(cut=True))
    trace = metrics.parse_abo_trace(log)
    assert (len(trace.episodes), trace.incomplete) == (1, 1)


@pytest.mark.unit
def test_abo_trace_without_alerts_has_no_episodes(tmp_path: Path) -> None:
    """Activations alone make a trace with no back-off and their top count."""
    log = tmp_path / "sim.log"
    log.write_text(
        "[PRAC] [3] [ACT] Row: 9 Act: 7\n[PRAC] [3] [ACT] Row: 9 Act: 8\n"
    )
    trace = metrics.parse_abo_trace(log)
    assert (trace.episodes, trace.incomplete) == ([], 0)
    assert trace.max_count_before_first == 8


@pytest.mark.unit
def test_abo_trace_skips_a_back_off_with_a_lost_transition(
    tmp_path: Path, prac_abo_log: Callable[..., str]
) -> None:
    """A transition that does not start from the current phase is not read."""
    lines = prac_abo_log().splitlines()
    lines = [x for x in lines if "-> <ABOState::RECOVERY>" not in x]
    log = tmp_path / "sim.log"
    log.write_text("\n".join(lines) + "\n")
    trace = metrics.parse_abo_trace(log)
    assert (len(trace.episodes), trace.incomplete) == (0, 1)


@pytest.mark.unit
def test_dram_timings_and_counters_are_read_from_the_log(
    tmp_path: Path,
) -> None:
    """The start-up timing lines and an end-of-run counter parse by name."""
    log = tmp_path / "sim.log"
    log.write_text(
        "[Ramulator::DDR5-VRR] nRAS: 52\n[Ramulator::DDR5-VRR] nRFM1: 560\n"
        "      prac_num_recovery: 18\n"
    )
    assert metrics.parse_dram_timings(log) == {"nRAS": 52, "nRFM1": 560}
    assert metrics.parse_counter(log, "prac_num_recovery") == 18
    with pytest.raises(ValueError, match="no counter"):
        metrics.parse_counter(log, "tprac_num_tb_rfm")
    log.write_text("nothing\n")
    with pytest.raises(ValueError, match="no DRAM timings"):
        metrics.parse_dram_timings(log)


TCK_NS = 0.625
"""DDR5-3200AN's clock period; 180 ns is 288 clocks."""

ABO_ACT_NS = 180
"""How long the controller may keep working after the alert (tABO_ACT)."""

ABO_ACT_MAX = 3
"""Activations the spec allows in that time (ABO_ACT)."""

RECOVERY_RFMS = 4
"""RFMab commands per rank in the recovery (PRAC-4, the spec's default)."""

BANKS = 64
"""Banks the recovery mitigates: 2 ranks of 32."""

SPEC_ROW_CYCLE_NS = 52
"""tRC under PRAC in the spec's timing table (tRAS 16 ns + tRP 36 ns)."""

SPEC_TIMINGS_NS = {"nRAS": 16, "nWR": 10, "nRTP": 5}
"""The spec's PRAC values for the timings the model leaves unshortened."""

SPEC_TIMING_CLOCKS = {"nRAS": 26, "nWR": 16, "nRTP": 8}
"""The same, in clocks, as a config override."""


@dataclasses.dataclass
class Runs:
    """PRAC proof-of-concept logs, each with the plugin's debug output on.

    - default: the tracked config (threshold 128).
    - low: threshold 64.
    - never: a threshold no row reaches.
    - spec_timing: the default with the spec's tRAS, tWR and tRTP.
    """

    default: Path
    low: Path
    never: Path
    spec_timing: Path


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory, traced_poc: Callable[..., Path]
) -> Runs:
    """Runs the four simulations once, in parallel, for this module."""
    root = tmp_path_factory.mktemp("prac-trace")

    def run(
        name: str, threshold: int, timing: Optional[Dict[str, int]]
    ) -> Path:
        """Runs PRAC's proof of concept with one threshold and timings."""
        plugins = {"PRAC": {"debug": True, "abo_threshold": threshold}}
        return traced_poc(root / name, "prac", plugins, timing)

    jobs = {
        "default": (128, None),
        "low": (64, None),
        "never": (100_000, None),
        "spec_timing": (128, SPEC_TIMING_CLOCKS),
    }
    with concurrent.futures.ThreadPoolExecutor(len(jobs)) as pool:
        futures = {n: pool.submit(run, n, *args) for n, args in jobs.items()}
        return Runs(**{n: f.result() for n, f in futures.items()})


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    ("which", "threshold"), [("default", 128), ("low", 64)]
)
def test_alert_fires_when_a_counter_reaches_the_threshold(
    runs: Runs, which: str, threshold: int
) -> None:
    """The first alert comes on the activation that makes a count N_BO.

    No row had a higher count before it, and every later alert was also raised
    by a count of at least N_BO: the threshold, not the attack, sets the moment.
    """
    log = getattr(runs, which)
    trace = metrics.parse_abo_trace(log)
    assert len(trace.episodes) > 10
    assert trace.incomplete == 0
    assert trace.max_count_before_first == threshold
    assert trace.episodes[0].trigger_count == threshold
    assert all(e.trigger_count >= threshold for e in trace.episodes)
    assert len(trace.episodes) == metrics.parse_counter(
        log, "prac_num_recovery"
    )


@pytest.mark.integration
@pytest.mark.slow
def test_no_alert_while_every_counter_is_below_the_threshold(
    runs: Runs,
) -> None:
    """The same attack raises nothing when N_BO is above what it reaches.

    The rows are hammered well past 128 in this run, so the quiet is the
    threshold's doing and not an attack that fell short.
    """
    trace = metrics.parse_abo_trace(runs.never)
    assert trace.episodes == []
    assert trace.max_count_before_first > 128
    assert metrics.parse_counter(runs.never, "prac_num_recovery") == 0


@pytest.mark.integration
@pytest.mark.slow
def test_each_back_off_follows_the_protocol(runs: Runs) -> None:
    """Window of 180 ns, then four RFMab per rank, then a delay of four ACTs.

    That is the alert, ABO_ACT window, PRAC-4 recovery and ABO_Delay of the
    spec, as the paper's tables give them.
    """
    timings = metrics.parse_dram_timings(runs.default)
    trace = metrics.parse_abo_trace(runs.default)
    assert trace.incomplete == 0
    for e in trace.episodes:
        assert (e.recovery_clk - e.assert_clk) * TCK_NS == ABO_ACT_NS
        assert e.window_acts <= ABO_ACT_MAX
        # Counts are the lines that survived guest output cutting a few.
        assert e.recovery_mitigations >= 0.99 * RECOVERY_RFMS * BANKS
        assert e.recovery_mitigations <= RECOVERY_RFMS * BANKS
        # The alerting row is among the mitigated ones.
        assert e.recovery_max_count >= e.trigger_count
        assert e.delay_acts == RECOVERY_RFMS
        # The recovery ends when the last RFM is issued; it then runs for tRFM.
        recovery = e.delay_clk - e.recovery_clk + timings["nRFM1"]
        assert recovery >= RECOVERY_RFMS * timings["nRFM1"]


@pytest.mark.integration
@pytest.mark.slow
def test_every_mitigation_takes_the_hottest_row_and_resets_it(
    runs: Runs,
) -> None:
    """Back-off RFMs follow the same rule as TPRAC's: hottest row, reset."""
    check = metrics.check_rfm_resets(runs.default)
    assert check.violations == []
    assert check.rfms >= 18 * RECOVERY_RFMS * BANKS * 0.99
    assert check.nonzero > 18


@pytest.mark.integration
@pytest.mark.slow
def test_prac_lengthens_the_precharge_and_the_row_cycle(runs: Runs) -> None:
    """tRP and tRC reach the spec's PRAC values (36 and 52 ns)."""
    timings = metrics.parse_dram_timings(runs.default)
    assert timings["nRP"] * TCK_NS >= 36
    assert abs(timings["nRC"] * TCK_NS - SPEC_ROW_CYCLE_NS) < 1


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: the model applies PRAC's timings with max() against the "
        "speed bin, so tRAS, tWR and tRTP are not shortened and the row "
        "cycle is 68.75 ns, not 52 ns. See docs/fidelity/prac.md."
    ),
)
@pytest.mark.parametrize("name", sorted(SPEC_TIMINGS_NS))
def test_shortened_timings_reach_the_spec_values(runs: Runs, name: str) -> None:
    """tRAS, tWR and tRTP are the spec's PRAC values (an expected failure).

    When the model is fixed this passes, and "strict" turns that into a
    failure that says to delete the marker and update the document.
    """
    timings = metrics.parse_dram_timings(runs.default)
    assert timings[name] * TCK_NS <= SPEC_TIMINGS_NS[name] + 1


@pytest.mark.integration
@pytest.mark.slow
def test_spec_timings_do_not_change_what_the_attack_sees(runs: Runs) -> None:
    """With the spec's timings the proof of concept raises the same alerts.

    Setting tRAS, tWR and tRTP by config override gives the spec's row cycle
    (tRAS + tRP) and leaves the decoded message and the number of back-offs as
    they are with the model's timings. Only the activations that fit in the
    alert window change.
    """
    default, spec = runs.default, runs.spec_timing
    timings = metrics.parse_dram_timings(spec)
    assert (timings["nRAS"] + timings["nRP"]) * TCK_NS - SPEC_ROW_CYCLE_NS < 1
    a, b = metrics.parse_poc(default), metrics.parse_poc(spec)
    assert (a.decoded_text, a.errors) == (b.decoded_text, b.errors)
    assert len(metrics.parse_abo_trace(default).episodes) == len(
        metrics.parse_abo_trace(spec).episodes
    )
    assert max(
        e.window_acts for e in metrics.parse_abo_trace(spec).episodes
    ) <= (ABO_ACT_MAX)
