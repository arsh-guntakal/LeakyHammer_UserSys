"""The ported plotters import cleanly and draw from stored results."""

from pathlib import Path

import pytest

from leakyhammer.plotting import noise_rfm, poc_dream, poc_rfm, poc_rrs


@pytest.mark.unit
def test_noise_plot_writes_figure_and_returns_numbers(
    data: Path, tmp_path: Path
) -> None:
    """The capacity-vs-noise plot is written and returns its headline values."""
    out = tmp_path / "f.pdf"
    numbers = noise_rfm.plot(data / "noise_ber_rfm.csv", out, 100, "RFM")
    assert out.stat().st_size > 1000
    assert set(numbers) == {"capacity_50pct", "capacity_lowest"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("module", "log"),
    [
        (poc_rfm, "rfm_poc.log"),
        (poc_dream, "dream_poc.log"),
        (poc_rrs, "rrs_poc.log"),
    ],
)
def test_poc_plots_draw_from_logs(
    module: object, log: str, data: Path, tmp_path: Path
) -> None:
    """Each POC plotter turns its log into a non-empty figure."""
    out = tmp_path / "f.pdf"
    module.plot(data / log, out)
    assert out.stat().st_size > 1000


@pytest.mark.unit
@pytest.mark.regression
def test_poc_plot_survives_non_utf8_bytes_in_log(
    data: Path, tmp_path: Path
) -> None:
    """A log with raw non-UTF-8 bytes still plots.

    Regression test: the RRS receiver prints decoded characters raw, so logs
    can contain bytes like 0x82, which crashed the plotter's strict decode.
    """
    log = tmp_path / "rrs.log"
    log.write_bytes((data / "rrs_poc.log").read_bytes() + b"\n\x82\x04\n")
    out = tmp_path / "f.pdf"
    poc_rrs.plot(log, out)
    assert out.stat().st_size > 1000
