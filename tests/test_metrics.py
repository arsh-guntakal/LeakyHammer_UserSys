"""Log parsing, BER, and capacity."""

import math
from pathlib import Path
from typing import Callable

import pytest

from leakyhammer import metrics


@pytest.mark.unit
def test_parse_log_reads_a_transmission(
    tmp_path: Path, transmission_log: Callable[..., str]
) -> None:
    """A transmission log parses to its bits, time, errors and health fields."""
    log = tmp_path / "x.log"
    log.write_text(transmission_log(errors=382))
    result = metrics.parse_log(log)
    assert result.ok
    assert len(result.sent) == len(result.received) == 800
    assert result.errors == 382
    assert result.txn_time_ns == 16019371
    assert (result.resyncs, result.min_sleep_assert) == (0, 6715)


@pytest.mark.unit
def test_parse_log_accepts_prefixed_tags(
    tmp_path: Path, transmission_log: Callable[..., str]
) -> None:
    """DREAM's "[DREAM-SEND]" tags parse like the plain "[SEND]" ones."""
    log = tmp_path / "x.log"
    log.write_text(transmission_log(errors=5, tag="DREAM"))
    assert metrics.parse_log(log).errors == 5


@pytest.mark.unit
def test_parse_log_counts_differing_bits(tmp_path: Path) -> None:
    """Errors are the number of positions where sent and received differ."""
    log = tmp_path / "x.log"
    log.write_text(
        "[SEND] Binary: 0101\n[RECV] Binary: 0111\n[RECV] Received in 10 ns\n"
    )
    result = metrics.parse_log(log)
    assert (result.errors, result.txn_time_ns) == (1, 10)


@pytest.mark.unit
def test_missing_or_crashed_log_is_not_ok(tmp_path: Path) -> None:
    """Missing logs and logs without bits are failures, not zero errors."""
    assert not metrics.parse_log(tmp_path / "absent.log").ok
    crashed = tmp_path / "crash.log"
    crashed.write_text("gem5 has encountered a segmentation fault!\n")
    assert metrics.parse_log(crashed).errors == metrics.PARSE_ERROR


@pytest.mark.unit
def test_length_mismatch_is_flagged(tmp_path: Path) -> None:
    """A receiver that decoded a different number of bits is a failure."""
    log = tmp_path / "x.log"
    log.write_text("[SEND] Binary: 0101\n[RECV] Binary: 01\n")
    assert metrics.parse_log(log).errors == metrics.LENGTH_MISMATCH


@pytest.mark.unit
def test_capacity_endpoints() -> None:
    """A noiseless channel keeps its raw rate; BER 0.5 carries nothing."""
    assert metrics.capacity_kbps(48.0, 0.0) == pytest.approx(48.0)
    assert metrics.capacity_kbps(48.0, 0.5) == pytest.approx(0.0)
    assert metrics.capacity_kbps(48.0, 1.0) == pytest.approx(48.0)
    assert metrics.binary_entropy(0.5) == pytest.approx(1.0)


@pytest.mark.unit
def test_raw_rate_matches_paper_formula() -> None:
    """800 bits in 16.019 ms is the 48.77 Kbps the report lists."""
    assert metrics.raw_kbps(800, 16019371) == pytest.approx(48.77, abs=0.01)


@pytest.mark.unit
@pytest.mark.regression
def test_summarize_refuses_failed_runs(tmp_path: Path) -> None:
    """A failed run must raise instead of being averaged in.

    Regression test: crashed runs parsed to "errors = -1" and were averaged
    with good ones, printing a raw rate of -781250000 Kbps.
    """
    good = metrics.SimResult("01", "01", 1000, 0)
    bad = metrics.SimResult()
    with pytest.raises(ValueError, match="1 of 2 runs failed"):
        metrics.summarize([good, bad], msg_bits=2)


@pytest.mark.unit
def test_summarize_uses_capacity_of_mean_ber() -> None:
    """Capacity comes from the mean BER, not the mean of per-run capacities."""
    results = [
        metrics.SimResult("0" * 100, "0" * 100, 1_000_000, 0),
        metrics.SimResult("0" * 100, "1" * 50 + "0" * 50, 1_000_000, 50),
    ]
    summary = metrics.summarize(results, msg_bits=100)
    assert summary.ber == pytest.approx(0.25)
    expected = summary.raw_kbps * (
        1 + 0.25 * math.log2(0.25) + 0.75 * math.log2(0.75)
    )
    assert summary.capacity_kbps == pytest.approx(expected)


@pytest.mark.unit
@pytest.mark.regression
def test_parse_poc_handles_dream_poc_tags(
    tmp_path: Path, poc_log: Callable[..., str]
) -> None:
    """DREAM's POC log uses a two-part "DREAM-POC-" tag and still decodes.

    Regression test: the log regexes allowed only one "PREFIX-" segment, so
    "[DREAM-POC-SEND]" lines were invisible and every DREAM POC "failed".
    """
    log = tmp_path / "dream.log"
    log.write_text(poc_log("dream", "UTECE", errors=18))
    result = metrics.parse_poc(log)
    assert result.sent_text == "UTECE"
    assert result.errors == 18
    assert result.resyncs == 0
    assert result.decoded_text != result.sent_text


@pytest.mark.unit
@pytest.mark.parametrize("defense", ["rfm", "rrs"])
def test_parse_poc_reads_per_window_format(
    defense: str, tmp_path: Path, poc_log: Callable[..., str]
) -> None:
    """With no final "Binary:" line, the per-window lines are decoded."""
    log = tmp_path / "poc.log"
    log.write_text(poc_log(defense, errors=3, binary=False))
    result = metrics.parse_poc(log)
    assert result.errors == 3
    assert result.sent_text == "MICRO"


@pytest.mark.unit
def test_parse_poc_falls_back_to_the_message_text(
    tmp_path: Path, poc_log: Callable[..., str]
) -> None:
    """A sender that prints only its message text still gives sent bits."""
    log = tmp_path / "poc.log"
    log.write_text(poc_log("prac").replace("[SEND] Binary:", "[SEND] ignored:"))
    assert metrics.parse_poc(log).sent_text == "MICRO"


@pytest.mark.unit
def test_parse_poc_rejects_garbage(tmp_path: Path) -> None:
    """An undecodable log raises, naming the file."""
    log = tmp_path / "bad.log"
    log.write_text("nothing useful\n")
    with pytest.raises(ValueError, match=r"bad\.log"):
        metrics.parse_poc(log)


@pytest.mark.unit
def test_text_bit_round_trip() -> None:
    """Text converts to bits and back; unprintable bytes show as '?'."""
    assert metrics.bits_to_text(metrics.text_to_bits("MICRO")) == "MICRO"
    assert metrics.bits_to_text("00000100") == "?"
