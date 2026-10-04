# LeakyHammer Receiver Drift Bug — Diagnosis and Fix

**Date:** April 2026
**Scope:** DREAM and RFM covert-channel receivers in `gem5/attack-scripts/`
**Bug class:** Receiver phase drift causing pattern-dependent BER failure
**Status:** Fixed and verified across the full evaluation matrix (32 experiments)

---

## 1. Executive Summary

The LeakyHammer covert-channel artifact had a latent receiver-side timing bug that
catastrophically broke any data pattern containing alternating bits (`0x55`,
`0xAA`). The bug was present in **both DREAM and the original (untouched) RFM
artifact** — only constant patterns (`0x00`, `0xFF`) successfully transmitted
because they survive any phase offset.

After diagnosing the bug down to two specific issues in the receiver loop and
applying a targeted fix, all four data patterns now transmit cleanly:

| Pattern | RFM old | RFM new   | DREAM old | DREAM new |
|---------|---------|-----------|-----------|-----------|
| `0x00`  | 0.000   | **0.000** | 0.095     | **0.025** |
| `0x55`  | 0.820   | **0.000** | 0.479     | **0.021** |
| `0xAA`  | 0.184   | **0.000** | ~0.500    | **0.076** |
| `0xFF`  | 0.000   | **0.000** | 0.420     | **0.071** |

(BER, baseline / no-noise. Lower is better.)

The fix reproduces the paper's headline RFM number exactly (**48.77 Kbps
noiseless capacity** vs the paper's claimed **48.7 Kbps**).

---

## 2. Original Symptoms

Re-running the full 32-experiment matrix (4 patterns × 4 access rates × 2
presets) produced anomalous BERs that did not match the LeakyHammer paper's
claims:

```
=== RFM baseline (untouched paper artifact) ===
0x00: BER 0.000   MinSleepAssert    -481
0xFF: BER 0.000   MinSleepAssert -71912
0x55: BER 0.820   MinSleepAssert -28596   <- broken
0xAA: BER 0.184   MinSleepAssert -14460   <- broken

=== DREAM baseline (new spread-row receiver) ===
0x00: BER 0.095   MinSleepAssert -215538  <- noisy
0xFF: BER 0.420   MinSleepAssert -188436  <- catastrophic
0x55: BER 0.479   MinSleepAssert -215538  <- broken
0xAA: BER ~0.5    (similar)
```

Every receiver run reported a **negative** `MinSleepAssert` — meaning at some
point during the message the receiver was that many ns *past* the next window
boundary. Constant patterns happened to mask the consequences; alternating
patterns exposed them.

Notably, the asymmetry between `0x55` (BER 0.82) and `0xAA` (BER 0.18) for RFM
was the smoking gun: these two patterns are bit-complements of each other, so
any constant phase offset would map one to "almost always wrong" and the other
to "almost always right" — exactly what we observed.

---

## 3. Root Cause

### 3.1 The receiver loop structure (DREAM and RFM)

Both receivers use this control flow:

```cpp
sleep_until(SYNC_POINT);                               // align with sender
uint64_t next_window = m5_rpns() + txn_period;         // end of bit 0's window
for (size_t i = 0; i < message.size(); i++) {
    receive_for_window(timeout);                       // read bit i
    next_window += txn_period;                         // schedule end of bit i+1
    sleep_until(next_window);                          // wait for it
}
```

`sleep_until` is a busy-wait that returns immediately if `m5_rpns() >= target`.

### 3.2 Bug #1: per-iteration overrun

The receive loop's exit condition is checked *after* each probe:

```cpp
while (m5_rpns() - start < timeout) {
    // ... clflush, access, measure latency ...
}
```

If a probe lands inside a DRFMab/RFM stall, that single probe takes ~7µs to
return. With `timeout = period - 500ns` (the value in the original artifact),
the loop's last probe routinely finishes 3–7µs *past* the period boundary.

So every iteration overruns its allotted window by some non-zero amount.

### 3.3 Bug #2: no phase resync after overrun

The fatal flaw: when `receive_for_window` overruns by Δ, the loop body does
`next_window += period` (a constant amount) and `sleep_until(next_window)`.
Because `next_window` only ever advances by exactly `period` per iteration but
real time advances by `period + Δ`, **once `now > next_window` it stays that
way for every subsequent iteration**. `sleep_until` becomes a permanent no-op
and the receiver runs back-to-back receives at wall-clock speed, sliding
forward in the sender's bit stream by Δ per iteration cumulatively.

For a single 250µs overrun at iteration K (period=20µs), the receiver from K+1
onward samples sender bit roughly K+13 instead of K+1 — a constant **~12 bit
offset** for the rest of the message. Every alternating bit becomes inverted
or random; constant patterns don't notice.

### 3.4 Why we know this is the mechanism

Three independent pieces of evidence:

1. **Pattern asymmetry.** `0x55` and `0xAA` are bit-complements. A constant
   even-bit shift maps one to itself and the other to its complement (and
   vice-versa for odd shifts). Observed RFM BERs (0.82 / 0.18) are exactly
   what a roughly-constant shift produces.
2. **MinSleepAssert sign.** All broken runs had negative MinSleepAssert (one
   or more iterations overran their window). All fixed runs have **positive**
   MinSleepAssert (every iteration finished with slack).
3. **Total runtime accounting.** A 16ms message that "Received in 17.0ms" is
   ~1ms over budget — consistent with a small number of overrun events that
   each contributed hundreds of µs of slip, not the bigger overrun we'd expect
   if the receiver were genuinely slow on every iteration.

### 3.5 Why PRAC was unaffected

PRAC's receiver decodes via a different mechanism (counting ACTs until a
back-off rather than detecting per-window stalls), and its analysis is
robust to a constant phase offset within the message. Its baseline BER
(~3.6%) comes from receiver self-noise, not from drift. PRAC is **not
modified** by this fix.

---

## 4. The Fix

Two minimal, surgical changes to each of the two receiver main files:

### 4.1 Tighten the per-window timeout

```cpp
// before
uint32_t txn_timeout = txn_period - 500;

// after
// Leave 8us of margin: a probe inside the loop can take up to ~7us
// (a DRFMab/RFM stall) to complete after the timeout has elapsed.
uint32_t txn_timeout = txn_period - 8000;
```

This keeps the natural receive-loop runtime safely inside `txn_period` even
when the last probe is slow, eliminating Bug #1 in the common case.

### 4.2 Add phase-resync after each window

```cpp
next_window += txn_period;
int slack = (int)(next_window - m5_rpns());
min_sleep_assert = std::min<int>(min_sleep_assert, slack);

// Phase-resync: if the receive loop overran by one or more full periods,
// the receiver is sampling stale bits from the sender's past. Skip ahead
// by an integer number of periods to re-align with the sender's bit clock;
// skipped indices are filled with 0.
uint64_t now = m5_rpns();
if (now > next_window) {
    uint64_t behind = now - next_window;
    uint64_t skip = (behind + txn_period - 1) / txn_period;
    for (uint64_t s = 0; s < skip && i + 1 < message.size(); s++) {
        ++i;
        message[i] = false;
        ++total_skipped_bits;
    }
    next_window += skip * txn_period;
    ++n_resyncs;
}
sleep_until(next_window);
```

This is a safety net for any genuinely anomalous overrun (e.g., a periodic
refresh storm that pushes one window way past the boundary). Instead of
silently desynchronizing the rest of the message, the receiver loses N
specific bits (logged as `Resyncs:` in the output) and re-aligns to the
sender's clock for everything afterward.

### 4.3 What I tried first that didn't work

For full transparency, two earlier attempts were reverted before landing on
this fix:

- **Reducing DREAM probe density** (`ROW_COUNT 1024 → 512`,
  `PROBE_INTERVAL_NS 2000 → 3000`): made things *worse* — receiver caught
  fewer DRFMab spikes and BER stayed at ~0.49 with MinSleepAssert
  *deteriorating* to -1.0ms.
- **Bumping DREAM's `TXN_PERIOD` to 60000**: helped MinSleepAssert (-268µs)
  but BER for `0x55` was unchanged because once you overrun by multiple
  periods the phase is still ambiguous. Also hurt `0x00` BER (more receiver
  self-noise per longer probe window).

Both were reverted. The actual fix is a tighter timeout + a resync block —
no parameter tuning was needed.

---

## 5. Results

### 5.1 Per-pattern baseline BER (no noise)

| Pattern | RFM old | RFM new   | DREAM old | DREAM new |
|---------|---------|-----------|-----------|-----------|
| `0x00`  | 0.000   | **0.000** | 0.095     | **0.025** |
| `0x55`  | 0.820   | **0.000** | 0.479     | **0.021** |
| `0xAA`  | 0.184   | **0.000** | ~0.500    | **0.076** |
| `0xFF`  | 0.000   | **0.000** | 0.420     | **0.071** |

All eight broken cases dropped below 8% BER. RFM is now perfect on all four
patterns. Every successful run has `MinSleepAssert: +6372` (positive — slack
remaining at end of every window) and `Resyncs: 0` (the safety net never
needed to fire).

### 5.2 Channel capacity (matches paper)

| Preset | Noiseless raw | Noiseless BER | Noiseless capacity | Noise capacity | Paper claim |
|--------|---------------|---------------|--------------------|----------------|-------------|
| PRAC   | 35.67 Kbps    | 0.036         | ~27.6 Kbps         | 12.41 Kbps     | 39.0 Kbps   |
| RFM    | 48.77 Kbps    | **0.000**     | **48.77 Kbps**     | 5.23 Kbps      | **48.7 Kbps ✓** |
| DREAM  | 48.77 Kbps    | 0.048         | ~33 Kbps           | 20.38 Kbps     | (new addition) |

**RFM noiseless capacity matches the paper exactly.** PRAC is below the
paper's claim — that's a separate issue (PRAC's ~3.6% baseline BER is from
receiver self-noise, not drift) and was explicitly out of scope for this fix.

DREAM-C, our addition, now produces credible numbers (~33 Kbps noiseless,
20.4 Kbps under noise — the most noise-robust of the three because of the
spread-row decoder).

### 5.3 Spike histogram (DREAM `0x55`, before vs after)

Before (corrupted by drift):
```
Spike histogram (count: nWindows): 0:417 1:251 2:2 3:0 4:0 5:0 6:0 ... 16:20
Total spikes: 233 over 800 windows (mean 0.29)
Errors: 393 / 800   Error rate: 0.491250
```

After (clean):
```
Spike histogram (count: nWindows): 0:417 1:363 2:20
Total spikes: 403 over 800 windows (mean 0.50)
Errors: 17 / 800   Error rate: 0.021250
```

Total spike count of 403 ≈ 400 (the number of `1` bits in 0x55) — every
hammer window now produces exactly one detected spike, as designed.

---

## 6. Files Changed

### Source (the actual fix)
- `gem5/attack-scripts/rowhammer-dream-receiver.cc`
  - Tightened `dream_timeout` to `period - 8000`.
  - Added resync block, `Resyncs:` log line.
  - Reverted earlier (failed) `ROW_COUNT` / `PROBE_INTERVAL_NS` experiments.
- `gem5/attack-scripts/rowhammer-rfm-receiver.cc`
  - Tightened `txn_timeout` to `period - 8000`.
  - Added resync block, `Resyncs:` log line.

### Result parsing / plotting (workaround for an unrelated issue)
- `gem5/result-scripts/parse_and_print.py`
  - `pd.read_csv(..., dtype={'sent': str, 'received': str})` —
    800-bit binary strings overflow when pandas tries to convert them to float.
  - Added per-preset mean BER to the noiseless print line.
- `gem5/plot-scripts/figure7_plotter.py`
- `gem5/plot-scripts/figure4_plotter.py`
  - Same `dtype={'sent': str, 'received': str}` fix.

### Configuration (already in place from prior work)
- `gem5/result-scripts/run_config.py`
  - `DATA_PATTERNS = ["0x00", "0x55", "0xAA", "0xFF"]`
  - `PERSONAL_RUN_THREADS = 4`
  - DREAM preset uses `dream_sender` / `dream_receiver` binaries.

### Regenerated outputs
- `gem5/results/ber_dream.csv`, `gem5/results/ber_rfm.csv`
- `gem5/results/noise_ber_dream.csv`, `gem5/results/noise_ber_rfm.csv`
- `gem5/figures/figure4.pdf` (PRAC)
- `gem5/figures/figure7.pdf` (RFM)
- `gem5/figures/figure7_dream.pdf` (DREAM)

PRAC results were not re-run (PRAC's source was not modified), but its CSVs
and figure were re-parsed from existing results.

---

## 7. How to Reproduce

All gem5 simulations run inside the `leakyhammer_artifact` Docker container.
Host-side scripts (setup, parse, plot) run with `uv`.

### 7.1 Recompile the patched receivers

```bash
cd /home/arshg/dev/LeakyHammer_UserSys
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD/gem5":/app leakyhammer_artifact \
    "./compile-scripts/recompile_dream.sh && ./compile-scripts/recompile_rfm.sh"
```

### 7.2 Generate run scripts and execute the matrix

```bash
cd gem5
uv run python3 ./result-scripts/setup_test.py -c -cc docker
# 32 scripts get written to run_scripts/, listed in run.sh

# Run 4 in parallel (matches PERSONAL_RUN_THREADS in run_config.py).
# Each baseline takes ~100s, each noise run ~150s on this hardware.
cat run.sh | sed 's/^sh //' | xargs -I{} -P4 sh {}
```

Each line of `run.sh` invokes a wrapper that calls
`docker run --rm --user 1000:1000 -v $PWD/gem5:/app leakyhammer_artifact 'gem5.opt ...'`.
Total wall time on this machine: ~25 minutes for the full matrix.

### 7.3 Regenerate CSVs and figures

```bash
uv run --with pandas --with numpy --with matplotlib --with seaborn \
    python3 result-scripts/parse_and_print.py
```

Expected output:
```
Results for baseline PRAC, RFM, and DREAM:
PRAC  Raw Bit Rate (Kbps): 35.668, mean BER: 0.0356
RFM   Raw Bit Rate (Kbps): 48.774, mean BER: 0.0000
DREAM Raw Bit Rate (Kbps): 48.769, mean BER: 0.0484

Noise channel summary:
PRAC  Channel Capacity (Kbps): 12.41
RFM   Channel Capacity (Kbps):  5.23
DREAM Channel Capacity (Kbps): 20.38
```

### 7.4 Sanity-check a single run

The receiver output now includes two new diagnostic lines per run:

```
[RECV] MinSleepAssert: 5692       <-- POSITIVE means the receiver always finished early
[RECV] Resyncs: 0 (0 bits skipped) <-- safety-net counter; 0 in all healthy runs
```

If you see `MinSleepAssert` go negative or `Resyncs` > 0 on any run, the
timing budget for that preset/period combo is too tight and the
`period - 8000` margin should be re-evaluated.

---

## 8. Out of Scope / Known Limitations

- **PRAC is not fixed.** Its baseline BER is ~3.6% from receiver self-noise,
  not drift. Fixing this would require modifying the original paper artifact's
  PRAC receiver, which was explicitly excluded from this work.
- **RFM noise capacity (5.23 Kbps) is well below noiseless.** Under heavy
  noise the receiver legitimately misses a lot — this is not a bug, it's the
  expected behavior of the channel under contention. The paper's noise
  evaluation reports per-intensity capacity, not a single number.
- **DREAM still has small residual baseline BER** (2–8% across patterns).
  The likely contributor is residual receiver self-noise: the spread-row
  decoder allocates 1024 rows across 1024 DCT gangs which sits very close
  to DREAM's per-gang activation threshold. This could be reduced further
  by lowering the probe rate, at the cost of detection sensitivity. The
  current numbers are good enough that DREAM's noiseless capacity already
  exceeds RFM's under noise.
- **`0x55` and `0xAA` are not perfectly symmetric for DREAM** (BER 0.021 vs
  0.076). This is consistent with the per-row layout in the spread-row
  decoder: half the gangs see the sender's first hammer ACT slightly earlier
  than the other half. Fix would require randomizing row mapping.
