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
  in the *same* bank can never share a counter. The sender therefore targets
  rows in two different bank groups chosen so that
  `row_a ^ mask[bank_a] == row_b ^ mask[bank_b]`, driving one shared counter to
  the threshold. Each target access is interleaved with a conflicting row in the
  same bank (and flushed), because re-reading an open row is a row hit and
  activates nothing.
- **Receiver**: probes 16,384 rows (stride 4) in its own bank, none in the
  sender's gang, so it does not trigger the counter itself. It records the
  number of latency spikes in the DRFMab band for every window and decodes
  against a threshold calibrated on a training preamble (8 quiet then 8 active
  windows), the midpoint of the two medians.
- **The masks must match.** The attack programs recompute the plugin's masks
  (`dream_compute_random_masks`, same seed and generator). The plugin prints its
  mask table at start-up (`grep "random_masks"` in `sim.log`); if the two ever
  disagree, the sender hammers the wrong gang and the channel silently closes.
- **Addresses.** The physical-address layout in `attacks/common/rowhammer-addr.hh`
  must match Ramulator's `RoBaRaCoCh_with_rit` mapper (bank group below bank, a
  64-bit address type). Getting this wrong earlier scrambled the DREAM sender's
  two-bank attack while leaving PRAC and RFM, which pin the all-ones bank, unaffected.
  The addresses reach about 17 GB; `--mem-size=32GB` is kept, though three trials gave
  identical results at 8 GB.

## What we measured

The first version of this attack reported a closed channel (BER 0.478 at
T_TH=40). That result was an artifact of the attack, not a property of DREAM-C;
see [attack-validity.md](attack-validity.md) for the four defects (the sender
never activated its rows, the receiver was misaligned by ~31 windows, the
decoder was blind to refresh noise, and a fixed spike count was the threshold).
The corrected attack is in `attacks/dream/`; its results below replace the old
table (BER 0.478 / 0.487 / 0.494 / 0.497 / 0.498 at T_TH 40-500). The old
behavior is at commit `bad71a9`.

Capacity is `raw * (1 - H(BER))`, with a raw rate of 47.81 Kbps (the training
preamble costs a little rate). Mean over 4 patterns of 100 bytes; "noise" is the
mean over the noise rates (3 per pattern):

| T_TH | Equivalent T_RH | Baseline BER | Baseline cap (Kbps) | Noise BER | Noise cap (Kbps) |
|---|---|---|---|---|---|
| 40 | 80 (below the paper's range) | 0.248 | 9.19 | 0.256 | 8.56 |
| 62 | 125 | 0.204 | 12.88 | 0.282 | 6.77 |
| 125 | 250 | 0.283 | 6.69 | 0.344 | 3.42 |
| 250 | 500 | 0.387 | 1.79 | 0.396 | 1.51 |
| 500 | 1000 | 0.473 | 0.10 | 0.400 | 1.40 |

So DREAM-C with random grouping leaks: a usable channel at low thresholds that
shrinks as T_TH grows. Do not over-read the trend. The threshold-500 noise row
beats its baseline, which is within the spread of four trials per cell, and the
low-threshold rows are limited by how many activations the sender can issue per
window, not only by the defense. The decoder is simple, so these are lower
bounds on what an attacker can do. `latency_histogram` shows the effect
directly: sent-1 windows have +1.2 (default T_TH) and +3.8 (T_TH=8) more slow
probes per window than sent-0 windows, against +3.3 for the RFM control.

For comparison, RFM is about 46.7 Kbps and PRAC about 13.5 Kbps at the same
noise rates. The `dream_threshold` config reproduces the table.

## Open questions

1. **Positive control.** Run with `grouping: set_assoc`. The DREAM paper argues
   this grouping produces hot counters and a usable channel. Comparing it with
   random grouping would show how much the random mask costs the attacker. It
   has not been run. Use `overrides: {grouping: set_assoc}` in a noise-sweep
   config.
2. **A smarter attacker.** Probing two bank groups and requiring simultaneous
   spikes (DRFMab is rank-wide, RFM is bank-wide), or correlating spike times
   with the sender's clock, might do better than the count threshold.
3. **Larger gangs.** Sweep `vertical_sharing` in 2, 4, 8. It was never measured.

The original working notes, including the full changelog, are in git history:
`git show f3b9dd6:docs/dream-history.md`.
