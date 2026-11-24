# PRAC: is it the specified defense?

What we model of Per Row Activation Counting, checked against what has been
published about it, with the deviations stated and each claim tied to a test or
a measurement. `docs/fidelity/tprac.md` covers TPRAC, which is built on this
model.

## Sources, and what was not read

PRAC is a feature of the JEDEC DDR5 specification (JESD79-5C, April 2024), not
a single paper. We did **not** read the JEDEC document (it is not freely
available). The description of the protocol comes from three sources that quote
it:

1. Canpolat et al., *Understanding the Security Benefits and Overheads of
   Emerging Industry Solutions to DRAM Read Disturbance* (DRAMSec 2024;
   arXiv 2406.19094v3). It analyses PRAC and open-sources an implementation in
   Ramulator 2.0. Its timing deltas and ABO parameters are used below.
2. Woo et al., the TPRAC paper (ISCA 2025; arXiv 2505.10111v3), Sec. 2.3, Table 1
   (ABO parameters) and Table 3 (simulated timings).
3. The TPRAC authors' artifact (`STAR-Laboratory/PRAC_TC_ISCA25`), read from the
   repository: its `DDR5-PRAC.cpp` and its Ramulator configurations.

The two papers were read from arXiv HTML through a summarizing fetch, not from
the PDFs, so section numbers and figures should be checked against the PDFs
before the appendix quotes them. The model's code comments cite "Table 343
JEDEC 79-5C_v1.30" for its timings; we have not checked that table, but its
values agree with both papers.

## Mechanism

| Specified behavior | Model | Evidence |
|---|---|---|
| Each row has an activation counter, incremented on every activation (the spec does it as a read-modify-write while the row precharges). | `PRAC::PerBankCounters::process_act` increments a per-row counter (sparse, per bank) on every ACT command. The increment is at the ACT, not the PRE. | Every logged ACT counts one more than the row's previous count. |
| When a counter reaches the back-off threshold N_BO, the device asserts Alert. | `process_act` marks the bank critical at `count >= abo_threshold`; the state machine asserts `ALERT_N` on the next tick. | `test_alert_fires_when_a_counter_reaches_the_threshold`: at thresholds 128 and 64 the first alert follows the activation that makes a count exactly N_BO, no row was higher before, and every later alert has a trigger of at least N_BO. |
| No alert while counters stay below N_BO. | Same. | `test_no_alert_while_every_counter_is_below_the_threshold`: with N_BO above anything reached, the same attack raises 0 alerts although rows reach 3,266 activations. |
| After the alert the controller may keep working for ABO_ACT: up to 3 activations, up to 180 ns (Table 1). | `abo_act_ns: 180` (288 clocks). The scheduler refuses any command that could not finish, with its closing precharge, before the recovery starts. | `test_each_back_off_follows_the_protocol`: the recovery starts exactly 288 clocks (180 ns) after the alert, and never more than 3 activations fit in the window. In the proof of concept none do (0 in all 18). |
| The recovery issues N_mit RFMab commands (1, 2 or 4; PRAC-4 is the JEDEC default), each blocking the rank for tRFMab = 350 ns. | `abo_recovery_refs: 4`; a PREA and four RFMab are queued for every rank. `nRFM1` is 560 clocks = 350 ns. | Same test: 256 mitigations per recovery (4 RFMs x 64 banks), and the recovery lasts at least 4 x 560 clocks. |
| An RFM mitigates the row with the maximum count in each bank (the spec leaves the queue to the vendor, but the papers assume this) and resets its counter. | `process_rfm` takes the maximum-count row of the bank and resets it. | `test_every_mitigation_takes_the_hottest_row_and_resets_it`: all 4,607 mitigations in a run, none violating the rule; 205 were on rows with count above 1. `test_each_back_off_follows_the_protocol`: the alerting row is among the rows each recovery mitigates. |
| After the recovery, a new alert needs ABO_Delay more activations, equal to N_mit (Table 1, footnote 3 of the first paper). | `abo_delay_acts: 4`. | Same test: every delay lasts exactly 4 activations. |
| One RFM refreshes four victim rows. | Not modeled; only the counter reset and the rank's stall. | See deviations. |

An alert stalls every rank of the channel in this model (a PREA and the RFMs to
each rank). The papers do not say how far the stall reaches: the first says "a
DRAM bank", the second does not say. This is the artifact's choice, and the one
the LeakyHammer attack depends on, since the receiver sits in a different bank
from the sender.

## Parameters

| Parameter | Specified | Model |
|---|---|---|
| N_BO | a fraction (70 to 100%) of the RowHammer threshold | 128 (`abo_threshold`) |
| ABO_ACT | 3 activations, 180 ns | 180 ns, as a scheduler constraint |
| N_mit (PRAC-N) | 1, 2 or 4 | 4 |
| ABO_Delay | equal to N_mit | 4 |
| tRFMab | 350 ns | 350 ns (560 clocks of 0.625 ns) |

## Timing: a gap, measured

PRAC changes the row cycle. Canpolat et al. give the deltas against DDR5-3200AN:
tRP +21 ns, tRAS -16 ns, tRTP -2.5 ns, tWR -20 ns, tRC +5 ns. The TPRAC paper's
Table 3 gives the resulting values: tRAS 16, tRP 36, tRTP 5, tWR 10, tRC 52 ns.

`DDR5-VRR.cpp` applies them as `max(PRAC value, speed bin's value)`, so only the
two *increases* take effect. Every run now prints the timings it ended up with
(`parse_dram_timings`):

| | Speed bin | PRAC spec | Model (measured) |
|---|---|---|---|
| tRAS | 32.5 ns | 16 ns | **32.5 ns** (52 clocks) |
| tRP | 15 ns | 36 ns | 36.25 ns (58 clocks) |
| tRTP | 7.5 ns | 5 ns | **7.5 ns** (12 clocks) |
| tWR | 30 ns | 10 ns | **30 ns** (48 clocks) |
| tRC, as configured | 46.9 ns | 52 ns | 51.9 ns (83 clocks) |
| Row cycle actually enforced (tRAS + tRP) | 47.5 ns | 52 ns | **68.75 ns** |

The effective row cycle is 32% longer than the spec's, because the tRAS +
tRP constraint, not `nRC`, is the binding one. The TPRAC authors' own
`DDR5-PRAC.cpp` has these `max()` lines commented out and assigns the five
values directly, so this is a known problem that they fixed; ours is the earlier
form. The three shortened values are checked by `test_shortened_timings_reach_the_spec_values`,
marked as an expected failure (strict), so fixing the model turns it into a
failure that says to update this table.

**Did it matter for the attack?** `test_spec_timings_do_not_change_what_the_attack_sees`
reruns the proof of concept with the spec's tRAS, tWR and tRTP (a config
override, not a code change; the row cycle becomes 52.5 ns):

| | Model's timings | Spec's timings |
|---|---|---|
| Alerts | 18 | 18 |
| Decoded message | `MICRO`, 0 errors | `MICRO`, 0 errors |
| Activations in the 180 ns window | 0 in 18 of 18 | 1 in 17 of 18 |

The proof of concept is unchanged. This was **not** measured for the noise
sweeps, which run far longer and under load, so their capacities may move; they
are the numbers the report quotes. The model is left as it is because the
report's results were produced with it (`docs/replication.md`); changing it
belongs in a separate PR that re-measures them.

## Deviations, on purpose or inherited

| Specified | Here | Consequence |
|---|---|---|
| Counters reset every tREFW (32 ms): the TPRAC paper's evaluation default; the first paper does not describe a reset. | No reset: only ACT and RFM are handled (the code has a `TODO` about PREs), so a counter falls only when an RFM mitigates its row. | None for runs shorter than tREFW: the proof of concept is about 1 ms and a noise-sweep trial sends for about 20 ms. Longer runs (SPEC benchmarks) accumulate counts. |
| The counter is read-modify-written at precharge. | Incremented at the ACT. | A shift of one tRAS in when a count is reached. |
| An RFM refreshes four victim rows. | Only the counter reset and the stall. | The receiver sees the stall, not the rows refreshed. |
| The spec lets the controller use up to 3 activations in the ABO window. | The scheduler refuses any command that cannot finish before the recovery, which leaves 0 in the proof of concept. | Fewer activations leak into the window than the spec allows; the controller design matches the first paper's ("delay requests that cannot be served within the window"). |
| `random_reset` | Available (random initial counters); off in the tracked config. | None. |

## What is not shown

- **The security guarantee.** Nothing here shows PRAC prevents bit flips, only
  that its counters, alert and recovery behave as described.
- **The spec itself.** Not read; see above.
- **The noise-sweep capacities under spec timings**, as noted.
- **Mutation testing.** A deliberately broken plugin was not built to show the
  simulator-level tests fail on it; the parsers are tested on good and bad
  synthetic traces.

## Reproducing

```
uv run pytest tests/test_prac.py     # 5 unit tests, then 4 simulator runs (~1 min)
```

The runs are the PRAC proof of concept with the plugin's `debug: true` at
thresholds 128 and 64, at a threshold nothing reaches, and with the spec's
timings. The simulator and the guest share one output stream, so a log line is
sometimes cut in half; the replay treats counts it reads as lower bounds and
flags only what they prove.
