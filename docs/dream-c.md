# DREAM-C

How the DREAM-C defense is modeled, how it is attacked, what we measured, and
what is still open. The plugin follows *DREAM: Enabling Low-Overhead Rowhammer
Mitigation via Directed Refresh Management* (Taneja and Qureshi, ISCA 2025), §5.

## The plugin

`gem5/ext/ramulator2/ramulator2/src/dram_controller/impl/plugin/dream.cpp`,
configured by `gem5/configs/rhsc/ramulator/dream.yaml`.

- One **DREAM Counter Table (DCT) per rank**, shared by all 32 banks of that
  rank. The paper's "sub-channel" is our rank (`DDR5_16Gb_x8` has 8 bank groups
  x 4 banks = 32 banks per rank). With `vertical_sharing: 1` the table has one
  entry per row of a bank (65,536), so a counter is shared by a *gang* of 32
  rows, one from each bank.
- **Grouping.** `random` (the paper's default) maps an activation to counter
  `(row XOR mask[bank]) mod entries`, with a random mask per bank, so rows in
  different banks that share a counter are unrelated. `set_assoc` uses
  `row mod entries`; it creates hot counters under the address mapping and is
  only useful as a comparison.
- **On every ACT** the plugin increments the counter. At `threshold` it issues
  `vertical_sharing` rank-wide `DRFMab` commands (about 280 ns of stall each) and
  resets the counter.
- **Reset** is gradual, one entry per rank every `reset_period_ns / entries`,
  instead of one bulk wipe each refresh window.

| Parameter | Meaning |
|---|---|
| `threshold` | `T_TH`. The paper uses `T_RH / 2`; the report's attacker-favorable value is 40 |
| `vertical_sharing` | 1, 2, 4, 8 -> gangs of 32 to 256 rows; DRFMab commands per hit |
| `grouping` | `random` or `set_assoc` |
| `seed` | Seeds the per-bank masks (the attack must use the same value) |
| `reset_period_ns` | tREFW, used to pace the reset |

**Deliberately not modeled:** the 32 ACT + Pre+S commands the paper issues
before each `DRFMab`. The DDR5-VRR model already accounts for the rank-wide
stall, which is all a user-space attacker can observe. Studying that overhead
itself would mean injecting those transactions with `priority_send`.

**Do not inflate the DRFM/RFM timings** in `DDR5-VRR.cpp` to make events more
visible. An earlier change did (5000 cycles), which pushed every RFM stall
outside the receivers' latency band and broke the RFM proof of concept.

## The attack

- **Sender** (`attacks/dream/`): because XOR with a mask is a bijection, two rows
  in the *same* bank can never share a counter. The sender therefore hammers
  rows in two different bank groups chosen so that
  `row_a ^ mask[bank_a] == row_b ^ mask[bank_b]`, driving one shared counter to
  the threshold.
- **Receiver**: probes 1,024 rows in its own bank, each in a different gang and
  none in the sender's, so it does not trigger the counter itself. It counts
  latency spikes in the DRFMab band per window and decodes a 1 when any appear.
- **The masks must match.** The attack programs recompute the plugin's masks
  (`dream_compute_random_masks`, same seed and generator). The plugin prints its
  mask table at start-up (`grep "random_masks"` in `sim.log`); if the two ever
  disagree, the sender hammers the wrong gang and the channel silently closes.
- **Addresses.** The physical-address layout in `attacks/common/rowhammer-addr.hh`
  must match Ramulator's `RoBaRaCoCh_with_rit` mapper (bank group below bank, a
  64-bit address type). Getting this wrong earlier scrambled the DREAM sender's
  two-bank attack while leaving PRAC and RFM, which pin the all-ones bank, unaffected.
  The two-bank attack also needs `--mem-size=32GB` (addresses reach about 17 GB).

## What we measured

With random grouping and `vertical_sharing: 1`, the attacker recovers almost
no channel. Capacity is `raw * (1 - H(BER))`, with a raw rate of 48.77 Kbps:

| T_TH | Equivalent T_RH | Baseline BER | Mean capacity under noise (Kbps) |
|---|---|---|---|
| 40 | 80 (below the paper's range) | 0.478 | 0.130 |
| 62 | 125 | 0.487 | 0.032 |
| 125 | 250 | 0.494 | 0.016 |
| 250 | 500 | 0.497 | 0.002 |
| 500 | 1000 | 0.498 | 0.001 |

For comparison, RFM is about 46.7 Kbps and PRAC about 13.5 Kbps at the same
noise rates. Capacity falls monotonically as `T_TH` grows, which fits the
explanation that a lower threshold fires `DRFMab` more often per hammer.

Treat these as a record, not a baseline to diff against: the `T_TH` 62-500 rows
were measured with the earlier harness and have **not been re-run** since the
reorganization (the `dream_threshold` config in `noise_sweep` runs the sweep;
T_TH=40 is reproduced by the default config). The explanation above is
consistent with the data but untested: nothing here proves *why* the channel
closes.

## Open questions

1. **Positive control (most valuable).** Run with `grouping: set_assoc`. The
   DREAM paper argues this grouping produces hot counters and a usable channel.
   A channel there would show the harness *can* detect DREAM leakage, ruling out
   "random grouping looks closed because the attack or decoder is broken". It has
   not been run. Use `overrides: {grouping: set_assoc}` in a noise-sweep config.
2. **A smarter attacker.** The decoder thresholds a per-window spike count in a
   fixed latency band. Probing two bank groups and requiring simultaneous spikes
   (DRFMab is rank-wide, RFM is bank-wide), or correlating spike times with the
   sender's clock, might recover a channel. "No usable channel" holds only for
   the attacker implemented here.
3. **Larger gangs.** Sweep `vertical_sharing` in 2, 4, 8. It should not help the
   attacker (the per-bank masks still hide the gang), but it was never measured.

The original working notes, including the full changelog, are in git history:
`git show f3b9dd6:docs/dream-history.md`.
