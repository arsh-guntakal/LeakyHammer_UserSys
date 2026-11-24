# TPRAC: is it the paper's defense?

What we implemented, line by line against the paper, what we deliberately left
out, and which tests show the code does what the paper says. The defense is
from *When Mitigations Backfire: Timing Channel Attacks and Defense for
PRAC-Based RowHammer Mitigations* (Woo, Qu, Saileshwar and Nair, ISCA 2025;
arXiv 2505.10111v3). `docs/tprac.md` covers how it is attacked and what the
attack measured; this file covers only fidelity.

**Provenance of the paper's numbers.** They were read from the arXiv v3 HTML
through a summarizing fetch, not from the PDF, so section numbers and figures
below should be checked against the PDF before the appendix quotes them. The
artifact numbers (`STAR-Laboratory/PRAC_TC_ISCA25`) were read from the
repository's files directly.

## Mechanism

| Paper | Code | Evidence |
|---|---|---|
| TB-RFMs are RFMab commands issued at fixed intervals, "independent of memory activity" (Sec. 4). | `tprac.cpp` `update()` sends one RFMab per rank when `m_clk == m_next_rfm_clk`, then adds one window. It reads no request or counter. | `test_rfms_are_periodic_whatever_the_activations`: every logged RFM is on `first + k * window`, both ranks at once, in a run where the sender hammers. |
| The TB-Window is the interval between consecutive TB-RFMs (Sec. 4). | `tb_rfm_window_ns`, converted with the DRAM clock: 3900 ns is 6240 clocks, 6070 ns is 9712. | Same test, at two windows (3900 ns, and 6070 ns, which is not a multiple of tREFI). |
| An RFMab stalls the rank for tRFMab = 350 ns (Table 3). | The DDR5 model's `nRFM1` is 560 clocks of 0.625 ns. The first RFM is placed at `window - nRFM1`, so it ends with its window, as in the authors' plugin. | The same test asserts `window_clk - first_clk` is 350 ns. (`docs/tprac.md` used to say 295 ns; that was wrong.) |
| Each RFM mitigates "the most frequently activated row in each DRAM bank", kept in a single-entry queue (Sec. 4.1), whether or not it reached the back-off threshold. | PRAC's `process_rfm` takes the bank's row with the maximum counter and resets it, on any RFMab it sees. TPRAC adds no queue of its own. | `test_each_rfm_mitigates_the_hottest_row_of_every_bank` replays PRAC's trace: 20,523 mitigations (32 banks x 644 RFMs is 20,608; the rest are banks with nothing to mitigate and lines cut by guest output), each on a count equal to the bank's maximum, each followed by a count of 1. 341 of them were on rows the attacker had hammered. |
| TB-RFMs keep counters below N_BO, so back-offs do not occur (Sec. 4). The paper does not describe what happens if one does. | The PRAC plugin is unchanged and still raises an ABO if a counter reaches `abo_threshold`. | `test_timing_based_rfms_replace_the_attacker_triggered_back_off`: the same run raises 18 ABOs with no RFM in the window and 0 with an RFM every 3900 ns. |
| The window is one 24-bit register (Sec. 6.8). | An `int` parameter. | Not applicable. |

## Parameters

| Parameter | Paper | Authors' artifact | This repository |
|---|---|---|---|
| Window at N_RH 1024 | about 6.2 us (1.6 tREFI) | `TB_RFM_window: 6070`, `abo_threshold: 995` | 3900 ns, `abo_threshold: 128` |
| Window at N_RH 512 | about 0.8 tREFI (3.1 us) | 2898, 481 | not run |
| Window at N_RH 256 / 128 | 4.3x / 6.4x more RFMs than at 1024 | 1442 / 974, with N_BO 222 / 80 | not run |
| Plugin default | not a paper parameter | `TB_RFM_window` default 3900 | 3900 (`tb_rfm_window_ns`) |

**The repository's pairing (3900 ns with N_BO 128) is not one the paper or the
artifact evaluates.** 3900 ns is the authors' plugin's default value, which
earlier documents here called "the paper's default". The paper chooses the
window from the worst-case (feinting) analysis for each threshold; for N_BO 128
that window is shorter than 3900 ns. So what the attack results show is that
*this* attacker (one row, hammered to the back-off threshold) loses its channel
at 3900 ns and shorter. They do not show that the configuration is secure
against the paper's worst-case attacker, and the appendix should not say so.

The 6070 ns run (the paper's window for N_RH 1024) is also ABO-free here
(`traced.paper`: 412 RFMs, 0 ABOs), but with N_BO 128 rather than 995, so it is
a different pairing again.

## Deviations, on purpose

| Paper or artifact | Here | Why it does not matter for the channel |
|---|---|---|
| The underlying PRAC is QPRAC with opportunistic mitigation, one RFM per alert (PRAC-1: `abo_delay_acts 1`, `abo_recovery_refs 1`). | The LeakyHammer artifact's PRAC: `abo_delay_acts 4`, `abo_recovery_refs 4`, a back-off of about 1.4 us. | PRAC is deliberately unchanged so TPRAC differs from PRAC only by the periodic RFMs; the control run (no RFM in the window) reproduces PRAC's results exactly. Absolute ABO latencies differ from the paper's. |
| A mitigation refreshes four victim rows and issues one aggressor ACT to reset the counter (Sec. 6.7). | Counter reset only. The stall is the RFM's tRFM. | The receiver sees the stall, not the rows refreshed. |
| Targeted refresh (TREF) can stand in for a TB-RFM in some intervals (Sec. 4.3). | Not modeled; the authors' plugin has it, and their TPRAC configurations leave it off. | The paper's default result is "without TREF". |
| `rfm_type` selects RFMab, RFMsb or RFMpb. | RFMab only. | RFMab is the default in every TPRAC configuration of the artifact. |
| Four ranks in the artifact's configurations. | Two. | Rank count does not change the schedule; the test checks both ranks fire together. |

## What is not shown

- **The security bound.** We do not reproduce the feinting analysis (the paper's
  worst-case activations to a target row, T_MAX) or its per-threshold windows.
  We use the artifact's windows as the reference.
- **A many-row attacker** against any window. The sender here hammers one row.
- **Performance.** The paper reports 3.4% average slowdown at N_RH 1024 (8.3%
  worst, on 433.milc). `spec_slowdown` measures TPRAC but at this repository's
  pairing, so it is not that number.
- **Mutation testing of the simulator-level tests.** The log checks are
  exercised on synthetic good and bad traces (unit tests), but a deliberately
  broken `tprac.cpp` was not built to show the simulator-level tests fail.

## Reproducing

```
uv run tools/compile-attacks tprac            # TPRAC's programs (PRAC's sources)
uv run pytest tests/test_tprac.py             # 7 unit tests, then 4 simulator runs (~2 min)
```

The simulator-level tests run the TPRAC proof of concept three times with the
plugin's `debug: true`: window 3900 ns (also with PRAC's debug output on, about
0.9 MB of log), window 6070 ns, and a 100 ms window that fires no RFM. The
simulator's output and the guest's share one stream, so a log line is
occasionally cut in half; the tests count that against a plugin counter that
cannot be corrupted (`tprac_num_tb_rfm`) rather than assuming every line
survived.
