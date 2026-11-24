"""TPRAC's behavior: parsing its trace, then the plugin against a simulator."""

import dataclasses
from pathlib import Path
from typing import Callable, Sequence

import pytest

from leakyhammer import metrics

TCK_NS = 0.625
"""DDR5-3200AN's clock period (1600 MHz); 3900 ns is 6240 clocks."""

TRFM_AB_NS = 350
"""tRFMab in the TPRAC paper's timing table; the RFM the plugin must model."""

RANKS = 2
"""Ranks per channel in the LeakyHammer configs."""

BANKS_PER_RANK = 32
"""Bank groups x banks per group of DDR5_16Gb_x8."""

PAPER_WINDOW_NS = 6070
"""The window the paper's authors pair with a threshold of 1024."""


@pytest.mark.unit
def test_trace_reports_every_rfm_and_the_counters(
    tmp_path: Path, tprac_trace_log: Callable[..., str]
) -> None:
    """The parsed trace has each RFMab's clock and rank and both counters."""
    log = tmp_path / "sim.log"
    log.write_text(tprac_trace_log(count=3, recoveries=2))
    trace = metrics.parse_tb_rfm_trace(log)
    assert (trace.window_ns, trace.window_clk, trace.first_clk) == (
        3900,
        6240,
        5680,
    )
    assert trace.rfms == tuple(
        (5680 + k * 6240, r) for k in range(3) for r in range(2)
    )
    assert (trace.num_recovery, trace.num_tb_rfm) == (2, 6)


@pytest.mark.unit
def test_trace_without_plugin_debug_output_is_refused(tmp_path: Path) -> None:
    """A log from a run without "debug: true" cannot be mistaken for no RFMs."""
    log = tmp_path / "sim.log"
    log.write_text("      prac_num_recovery: 0\n      tprac_num_tb_rfm: 0\n")
    with pytest.raises(ValueError, match="no TPRAC debug output"):
        metrics.parse_tb_rfm_trace(log)


def _check(
    tmp_path: Path,
    prac_debug_log: Callable[..., str],
    events: Sequence[Sequence[object]],
) -> metrics.RfmResetCheck:
    """Writes the events as a PRAC debug log and checks its RFMs."""
    log = tmp_path / "sim.log"
    log.write_text(prac_debug_log(events))
    return metrics.check_rfm_resets(log)


@pytest.mark.unit
def test_rfm_of_the_hottest_row_is_accepted(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """An RFM that takes the bank's maximum and resets it passes the check."""
    result = _check(
        tmp_path,
        prac_debug_log,
        [
            ("act", 5, 10, 1),
            ("act", 5, 10, 2),
            ("act", 5, 11, 1),
            ("rfm", 5, 10, 2),
            ("act", 5, 10, 1),
            ("act", 6, 10, 1),
        ],
    )
    assert (result.rfms, result.nonzero) == (1, 1)
    assert (result.violations, result.desyncs) == ([], 0)


@pytest.mark.unit
def test_rfm_of_a_cooler_row_is_a_violation(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """Mitigating a row below the bank's maximum (say, the oldest) fails."""
    result = _check(
        tmp_path,
        prac_debug_log,
        [
            ("act", 5, 11, 1),
            ("act", 5, 10, 1),
            ("act", 5, 10, 2),
            ("act", 5, 10, 3),
            ("rfm", 5, 11, 1),
        ],
    )
    assert len(result.violations) == 1
    assert "maximum is 3" in result.violations[0]


@pytest.mark.unit
def test_rfm_that_leaves_the_counter_is_a_violation(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """If the row keeps counting from where it was, the RFM did not reset it."""
    result = _check(
        tmp_path,
        prac_debug_log,
        [
            ("act", 5, 10, 1),
            ("act", 5, 10, 2),
            ("rfm", 5, 10, 2),
            ("act", 5, 10, 3),
        ],
    )
    assert len(result.violations) == 1
    assert "did not reset" in result.violations[0]


@pytest.mark.unit
def test_rfm_count_below_the_activations_seen_is_a_violation(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """An RFM reporting fewer activations than the log shows fails."""
    result = _check(
        tmp_path,
        prac_debug_log,
        [
            ("act", 5, 10, 1),
            ("act", 5, 10, 2),
            ("act", 5, 10, 3),
            ("rfm", 5, 10, 2),
        ],
    )
    assert len(result.violations) >= 1


@pytest.mark.unit
def test_rfm_count_above_the_log_is_a_lost_line_not_a_violation(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """Guest output cuts an activation line now and then, so the log's counts
    are lower bounds. An RFM reporting more than the log shows is a lost line.
    """
    result = _check(
        tmp_path,
        prac_debug_log,
        [("act", 5, 10, 1), ("act", 5, 10, 2), ("rfm", 5, 10, 4)],
    )
    assert (result.violations, result.desyncs) == ([], 1)


@pytest.mark.unit
@pytest.mark.regression
def test_rfm_of_a_row_with_no_logged_activation_is_accepted(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """An RFM line for a row the log never showed activated once crashed.

    The replay indexed the row's count directly, so the first RFM on a row
    with no logged activation (count 0) raised "KeyError".
    """
    result = _check(tmp_path, prac_debug_log, [("rfm", 5, 7, 0)])
    assert (result.rfms, result.violations) == (1, [])


@pytest.mark.unit
def test_line_clobbered_by_guest_output_is_not_a_violation(
    tmp_path: Path, prac_debug_log: Callable[..., str]
) -> None:
    """The simulator's output interleaves with the guest's; one lost line.

    The log really contains lines cut in half by a guest "printf", so a
    missing activation shows as a gap in a row's count. It is reported as a
    desync and the replay continues from the logged count.
    """
    result = _check(
        tmp_path,
        prac_debug_log,
        [
            ("act", 5, 10, 1),
            ("act", 5, 10, 3),
            ("rfm", 5, 10, 3),
            ("act", 5, 10, 1),
        ],
    )
    assert (result.violations, result.desyncs) == ([], 1)


@dataclasses.dataclass
class Traces:
    """The traced runs: the default window, the paper's, and a no-RFM control.

    - default_log (Path): the default run's log, which also traces PRAC.
    """

    default: metrics.TbRfmTrace
    paper: metrics.TbRfmTrace
    control: metrics.TbRfmTrace
    default_log: Path


@pytest.fixture(scope="module")
def traced(
    tmp_path_factory: pytest.TempPathFactory, traced_poc: Callable[..., Path]
) -> Traces:
    """Runs the traced simulations once for all the tests in this module."""
    root = tmp_path_factory.mktemp("tprac-trace")

    def run(name: str, window: int, prac_debug: bool) -> Path:
        """Runs TPRAC's proof of concept with one window."""
        return traced_poc(
            root / name,
            "tprac",
            {
                "TPRAC": {"tb_rfm_window_ns": window, "debug": True},
                "PRAC": {"debug": prac_debug},
            },
        )

    # PRAC's own trace is on for one run only: it is large, and replaying
    # one run is enough to check what an RFM does to the counters.
    default = run("default", 3900, True)
    paper = run("paper", PAPER_WINDOW_NS, False)
    # A window longer than the run fires no RFM, leaving PRAC alone.
    control = run("control", 100_000_000, False)
    return Traces(
        metrics.parse_tb_rfm_trace(default),
        metrics.parse_tb_rfm_trace(paper),
        metrics.parse_tb_rfm_trace(control),
        default,
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("which", ["default", "paper"])
def test_rfms_are_periodic_whatever_the_activations(
    traced: Traces, which: str
) -> None:
    """One RFMab per rank every window, at the same clock, without a gap.

    The window is in nanoseconds and need not be a multiple of tREFI (the
    paper's is not), so the cadence is checked in clocks. The first RFM is
    placed so that it finishes at the end of the first window.
    """
    trace = getattr(traced, which)
    assert trace.window_clk * TCK_NS == trace.window_ns
    # tRFMab is the distance from the first RFM to the end of its window.
    assert (trace.window_clk - trace.first_clk) * TCK_NS == TRFM_AB_NS
    # The plugin's counter is exact; the log is not, because the guest's own
    # output cuts a line in half now and then. So every logged RFM must be on
    # the schedule, and nearly all of the counted ones must be in the log.
    rounds = trace.num_tb_rfm // RANKS
    assert rounds > 100
    schedule = {trace.first_clk + k * trace.window_clk for k in range(rounds)}
    assert trace.num_tb_rfm == RANKS * rounds
    assert {clk for clk, _ in trace.rfms} <= schedule
    assert len(set(trace.rfms)) == len(trace.rfms)
    assert {rank for _, rank in trace.rfms} == set(range(RANKS))
    assert len(trace.rfms) >= 0.95 * trace.num_tb_rfm


@pytest.mark.integration
@pytest.mark.slow
def test_each_rfm_mitigates_the_hottest_row_of_every_bank(
    traced: Traces,
) -> None:
    """Every RFMab takes each bank's most-activated row and resets it.

    This is the single-entry frequency-based queue of the paper, replayed
    from PRAC's own trace: 32 banks per rank, 2 ranks, for every RFM.
    """
    check = metrics.check_rfm_resets(traced.default_log)
    expected = traced.default.num_tb_rfm * BANKS_PER_RANK
    assert check.violations == []
    assert 0.99 * expected <= check.rfms <= expected
    # Some of those mitigations hit a row the attacker had hammered.
    assert check.nonzero > 100


@pytest.mark.integration
@pytest.mark.slow
def test_timing_based_rfms_replace_the_attacker_triggered_back_off(
    traced: Traces,
) -> None:
    """Without the RFMs PRAC raises back-offs; with them it raises none.

    Same programs, same PRAC plugin and threshold: the only difference
    between the control and the default run is the timing-based RFMs.
    """
    assert traced.control.num_tb_rfm == 0
    assert traced.control.num_recovery > 0
    assert traced.default.num_recovery == 0
