> **Historical record.** This is the project's working notes from before the
> repository was reorganized (it used to be `AGENTS.md`). It is kept for the
> DREAM-C design rationale (sections 5-6), the changelog, and the original
> result tables. Its commands and paths describe the old layout
> (`gem5/result-scripts`, `gem5/attack-scripts`, per-run docker mounts) and no
> longer work: use `README.md` and `CLAUDE.md` instead. Numbers below were
> measured with the pre-reorganization harness; see the README for the current
> reproduction and how they compare.

# AGENTS.md — LeakyHammer + DREAM-C User-Sys Workspace

This file gives a fresh LLM session everything it needs to be productive in
this repository. Read this first.

---

## 1. What this project is

This repo extends the official artifact for the MICRO 2025 paper
**"Understanding and Mitigating Covert and Side Channel Vulnerabilities
Introduced by RowHammer Defenses"** (Bostancı et al., ETH Zürich /
[arXiv:2503.17891](https://arxiv.org/pdf/2503.17891)). The paper introduces
**LeakyHammer**, a class of attacks that turn DRAM RowHammer *defenses* into
timing covert channels and side channels.

We have:

1. The original LeakyHammer artifact (gem5 + Ramulator2, two RowHammer
   defenses: PRAC and RFM, plus a website-fingerprinting side channel).
2. **A new defense, DREAM-C, that we ported in from a separate paper
   (`DREAM.pdf` in the repo root) and integrated into the same
   evaluation harness.**

The point of the work is to evaluate whether DREAM-C — a more recent,
counter-based RowHammer mitigation — is more or less leaky than the
industry-standard PRAC/RFM defenses, using the LeakyHammer methodology.

### 1.1 The LeakyHammer paper in one paragraph

RowHammer is a DRAM bug where repeatedly activating a row causes bit flips
in nearby rows. Defenses like **PRAC** (Per-Row Activation Counting) and
**RFM** (Refresh Management) prevent flips by issuing extra refresh commands
when a row gets hit too often. These extra refreshes block memory accesses,
making them slower. LeakyHammer's insight: a **sender** process can
deliberately hammer a row to trigger one of these refreshes, and a
**receiver** process on the same machine can detect the resulting latency
spike. Sender and receiver both run on a simulated multi-core gem5 system
sharing one DRAM. Send a `1` by hammering, send a `0` by sleeping; receiver
probes a few rows every ~µs and decodes bits from the latency it sees. The
paper measures channel capacity (Kbps) at various noise levels.

### 1.2 The three defenses in this repo

| Preset | Source | What it does | Status in our repo |
|--------|--------|--------------|---------------------|
| **PRAC** | LeakyHammer artifact | Tracks per-row ACT count; triggers a "back-off" refresh once a counter saturates | Untouched original |
| **RFM**  | LeakyHammer artifact | Memory controller issues periodic RFM commands proportional to recent ACT count | Receiver patched (drift fix, see §6) |
| **DREAM-C** | Ported from `DREAM.pdf` | Counts ACTs at *gang* (group of rows that map to one shared counter via random per-bank XOR mask) granularity; issues `DRFMab` (Directed Refresh Management, all banks) when a gang counter saturates | New addition: Ramulator plugin + new sender/receiver binaries + receiver patched. **Plugin rewritten 2026-04-25; harness address-mapping fixed + full paper-range T_TH sweep completed 2026-04-26/27 — see §5.1 + §5.1.2 changelog.** Empirical result: monotone-decreasing capacity in T_TH; ≤ 0.15 Kbps at T_TH=40 (sub-paper) and ≤ 0.04 Kbps at every paper-faithful T_TH ∈ {62, 125, 250, 500} — dropping to ~0.001 Kbps at the paper-max T_TH=500 (§6 + §6.1). |

DREAM-C uses the JEDEC-standard DRFMab command path that already existed in
the Ramulator2 DDR5-VRR model.

---

## 2. Repository layout

```
LeakyHammer_UserSys/
├── README.md                       # Original artifact README (paper authors')
├── LeakyHammer.pdf                 # The paper
├── DREAM.pdf                       # Paper for the DREAM mitigation we ported
├── RECEIVER_DRIFT_FIX.md           # Detailed writeup of our receiver bug + fix
├── DREAM_INTEGRATION_REPORT.md     # **OUTDATED — do not trust.**
├── AGENTS.md                       # This file
├── leakyhammer_artifact.tar        # Pre-built Docker image (~452 MB)
├── Dockerfile                      # If you ever need to rebuild the image
├── container_setup.sh              # First-time environment setup
└── gem5/                           # Everything that actually runs
    ├── attack-scripts/             # C++ source for senders/receivers
    │   ├── rowhammer-side.cc/.hh   # Shared library: probe loops, hammer routines
    │   ├── rowhammer-prac-{sender,receiver}.cc
    │   ├── rowhammer-rfm-{sender,receiver}.cc
    │   ├── rowhammer-dream-{sender,receiver}.cc   # Our addition
    │   └── rowhammer-mr-noise.cc                  # The "noise generator" 3rd process
    ├── attack-binaries/            # Compiled outputs of attack-scripts/
    ├── compile-scripts/            # Per-target recompile shells
    │   ├── recompile_rfm.sh
    │   ├── recompile_dream.sh      # Our addition
    │   └── ...
    ├── compile_attack_scripts.sh   # Compiles all attack binaries at once
    ├── configs/rhsc/ramulator/     # Ramulator2 YAML configs per defense
    │   ├── prac.yaml
    │   ├── rfm.yaml
    │   └── dream.yaml              # Our addition
    ├── ext/ramulator2/             # Ramulator2 source (vendored)
    │   └── ramulator2/src/dram_controller/impl/plugin/dream.cpp  # Our DREAM-C plugin
    ├── result-scripts/             # Python: orchestrate experiments + parse results
    │   ├── run_config.py           # **Edit this to change what runs.**
    │   ├── setup_test.py           # Generates run_scripts/*.sh and run.sh
    │   ├── parse_and_print.py      # Parses log txts → CSVs, prints summary, calls plotters
    │   └── execute_run_script.py   # Wrapper that local runners invoke
    ├── plot-scripts/               # Python: generate the paper's PDF figures
    │   ├── figure4_plotter.py      # PRAC noiseless results
    │   ├── figure7_plotter.py      # RFM (and our DREAM) results
    │   ├── figure6_dream_plotter.py # DREAM POC sanity figure (our addition)
    │   └── figure{2,3,6}_plotter.py  # Other paper figures (less relevant for us)
    ├── run_scripts/                # **Generated** per-experiment shell scripts
    ├── run.sh                      # **Generated** master list (one `sh run_scripts/...` per line)
    ├── results/                    # Per-experiment output txts + final CSVs
    │   ├── prac/{baseline,noise}/
    │   ├── rfm/{baseline,noise}/
    │   ├── dream/{baseline,noise}/
    │   └── ber_*.csv, noise_ber_*.csv     # Aggregated results
    ├── figures/                    # PDF outputs of the plotters
    └── build/X86/gem5.opt          # Built simulator (inside Docker)
```

---

## 3. The experiment matrix

`gem5/result-scripts/run_config.py` defines what runs. Current settings:

```python
PERSONAL_RUN_THREADS = (
    4  # parallel docker containers (DON'T crank past 4 — OOM risk)
)
MSG_BYTES = 100  # 800 bits per message
DATA_PATTERNS = [
    "0x00",
    "0x55",
    "0xAA",
    "0xFF",
]  # alternating + constant bit patterns
```

Per-preset parameters (in the `get_preset_variables()` function):

| Preset | TXN_PERIOD (ns) | Sender binary  | Receiver binary  | Noise rates (ACTs/window) |
|--------|-----------------|----------------|------------------|----------------------------|
| PRAC   | 25 000          | `prac_sender`  | `prac_receiver`  | `[275, 475, 1075, 1975]`   |
| RFM    | 20 000          | `rfm_sender`   | `rfm_receiver`   | `[200, 263, 325]`          |
| DREAM  | 20 000          | `dream_sender` | `dream_receiver` | `[200, 263, 325]`          |

A single experiment looks like:
- 2 (or 3, with noise) gem5 processes share one simulated DDR5 channel.
- Sender hammers a row to send `1`, idles for `0`, one bit per `TXN_PERIOD` window.
- Receiver probes rows every `PROBE_INTERVAL_NS` and counts latency spikes.
- Optional noise generator hits memory at `access_rate` ACTs/window.
- Each run is one process tree inside a `docker run`, takes ~100–150s.

Total matrix = 4 patterns × 4 access rates × 3 presets ≈ 32 baseline + 36 noise
runs (we currently only re-run RFM and DREAM since PRAC source is untouched).

---

## 4. Top-level workflow (the "just run it" path)

All commands assume you are at the repo root.

### 4.1 First time only — load Docker image

```bash
docker load -i leakyhammer_artifact.tar
```

### 4.2 (Re)compile inside the container

There are **two independent build artifacts**, and which one you need to
rebuild depends on what you changed:

| You edited... | Then rebuild...                  | Command |
|---|---|---|
| C++ in `gem5/attack-scripts/` | the userspace sender/receiver binaries | `./compile_attack_scripts.sh` (all) or `./compile-scripts/recompile_<preset>.sh` (one) |
| C++ in `gem5/ext/ramulator2/...` (e.g. `DDR5-VRR.cpp`, `dream.cpp`, any plugin) | `libramulator.so` only | `./rebuild.sh --ramulator` |
| Public ABI of `libramulator.so` (function signature on an exported symbol, or a header included from gem5) | `libramulator.so` **and** relink `gem5.opt` | `./rebuild.sh --all` (or `--ramulator` then `--gem5`) |
| YAML in `gem5/configs/` | nothing — configs are read at runtime | (no rebuild) |

> **Heads-up on `compile_attack_scripts.sh`:** until 2026-04-26 it did **not**
> recompile the DREAM POC binaries (`dream_poc_sender`/`dream_poc_receiver`).
> If you edit `dream-poc-{sender,receiver}.cc` or anything in
> `rowhammer-side.{cc,hh}` / `rowhammer-addr.hh` that affects the POC, run
> `./compile-scripts/recompile-dream-poc.sh` explicitly. Symptom of forgetting:
> POC binaries silently keep their old behaviour despite header changes.

> **Memory-size note (DREAM only).** After the 2026-04-26 address-mapping fix
> (§5.1.2) the DREAM sender's two-bank gang-collision attack synthesises
> physical addresses up to ~17 GB, so `--mem-size` was raised from `8GB` to
> `32GB` in `poc-scripts/dream_poc_utece.sh` and `result-scripts/run_config.py`.
> `--mem-size` only sets the address-space ceiling — it doesn't change DRAM
> timing — so PRAC/RFM results are bit-invariant under this change.

`gem5.opt` dynamically links `libramulator.so` (`gem5/ext/ramulator2/SConscript`
sets `LIBS=['ramulator']` + `RPATH=[ramulator2_path]`), so for any change that
*only* touches Ramulator's internal source files (DRAM model timing values,
plugin internals, scheduler internals, etc.) `--ramulator` is enough — the
next `gem5.opt` invocation picks up the rebuilt `.so`. You only need `--all`
when you change something gem5 itself compiles against.

So a typical "I changed the DREAM plugin" cycle is:

```bash
# 1. Rebuild just Ramulator (~1-2 min):
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD/gem5":/app leakyhammer_artifact \
    "./rebuild.sh --ramulator"

# 2. Optionally rebuild attack binaries too if you also touched attack-scripts/:
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD/gem5":/app leakyhammer_artifact \
    "./compile_attack_scripts.sh"
```

You can sanity-check that the rebuild actually happened by comparing
`stat -c '%y' gem5/ext/ramulator2/ramulator2/libramulator.so` against the
mtime of the file you edited — `libramulator.so` should be *newer* than your
source change.

> **Build flavor note:** `rebuild.sh` always builds Ramulator with
> `-DCMAKE_BUILD_TYPE=Debug`. The `libramulator.so` originally baked into the
> Docker image (`leakyhammer_artifact.tar`) was almost certainly Release. This
> doesn't change *correctness* (DRAM timing is in mem-cycles, fully
> deterministic), but it can shift per-window event counts vs. the originally
> shipped figures (e.g. exact `[RECV] (N RFMs)` counts in the RFM POC differ
> slightly from `figures/figure6bak.pdf` even though the decoded bits match
> 1:1). If you need exact-count parity, change `-DCMAKE_BUILD_TYPE=Debug` to
> `Release` in `rebuild.sh` and nuke `gem5/ext/ramulator2/ramulator2/build/`
> before rebuilding.

### 4.3 Generate the run scripts

```bash
cd gem5
uv run python3 ./result-scripts/setup_test.py -c -cc docker
```

This (re)creates `run_scripts/*.sh` (one per experiment) and rewrites
`run.sh` with one `sh run_scripts/...` line per script. The `-cc docker`
flag makes each generated script wrap its gem5 invocation in
`docker run --rm --user 1000:1000 -v $PWD/gem5:/app leakyhammer_artifact 'gem5.opt ...'`.

### 4.4 Execute the matrix in parallel

```bash
cat run.sh | sed 's/^sh //' | xargs -I{} -P4 sh {}
```

`-P4` matches `PERSONAL_RUN_THREADS = 4`. Wall time ~25 min for the full RFM
+ DREAM matrix on a beefy desktop. **Do not raise to 16 — we OOM'd.**

Per-experiment output goes to `results/<preset>/<baseline|noise>/<stat>.txt`.

### 4.5 Parse, summarize, and plot

```bash
uv run --with pandas --with numpy --with matplotlib --with seaborn \
    python3 result-scripts/parse_and_print.py
```

This walks `results/`, builds `results/ber_*.csv` and `results/noise_ber_*.csv`,
prints a summary to stdout, and calls the plotters in `plot-scripts/` to
write `figures/figure*.pdf`.

Expected summary on a healthy run (post-Path-A, see §5.1.2 / §6):

```
Results for baseline PRAC, RFM, and DREAM:
PRAC  Raw Bit Rate (Kbps): 39.015  mean BER: 0.0356
RFM   Raw Bit Rate (Kbps): 48.770  mean BER: 0.1972
DREAM Raw Bit Rate (Kbps): 48.769  mean BER: 0.4781

Noise channel capacity (BER-adjusted, mean over the 3- or 4-rate subset):
PRAC: ~13.47 Kbps   RFM: ~46.71 Kbps   DREAM: ~0.13 Kbps
```

The RFM "baseline BER worse than under-noise BER" is a known artefact of
the post-revert detection band on the all-1s `0xFF` pattern — see §6.

---

## 5. The DREAM-C addition (what we built)

### 5.1 Ramulator plugin (paper-accurate rewrite, 2026-04)

`gem5/ext/ramulator2/ramulator2/src/dram_controller/impl/plugin/dream.cpp`
implements an `IControllerPlugin` named `DREAM`. **The plugin was rewritten
on 2026-04-25 to match the design in `DREAM.pdf` §5. Results from before
that date are not directly comparable** — see the changelog at the end of
this section.

The new design:

- One **DREAM Counter Table (DCT) per sub-channel**, *shared across all
  banks of that sub-channel*. We map each rank in the gem5/Ramulator
  config to one DDR5 sub-channel (JEDEC DDR5: 32 banks per sub-channel;
  our `DDR5_16Gb_x8` preset gives BG=8 × BA=4 = 32 banks per rank, so
  rank ≡ sub-channel cleanly).
- **DCT size**: `num_rows_per_bank / vertical_sharing` entries per
  sub-channel (e.g. 65 536 entries with `vertical_sharing=1` for our
  DDR5_16Gb_x8). Stored as a flat `std::vector<int>` (≈260 KB of host
  RAM total — tiny).
- **Grouping function** is selectable via the `grouping` YAML key:
  - `random` (default, paper §5.2): `idx = (RowID XOR mask[bank]) mod
    num_entries`. Each bank within the sub-channel has a randomly
    initialized `mask[bank]`. Breaks the spatial correlation between
    RowIDs across banks (which under MOP4 mapping otherwise produces hot
    counters; see paper Fig. 13a).
  - `set_assoc` (paper §5.2 baseline): `idx = RowID mod num_entries`.
    Hot-counter prone — only useful as a comparison.
- **On every ACT**: increment the addressed counter; if it reaches the
  `threshold`, issue `vertical_sharing` `DRFMab` commands back-to-back
  (rank-scope, ~280 ns stall each) and reset the counter to 1.
- **DCT reset**: gradual round-robin — one entry per sub-channel reset
  every `reset_period_clk / num_entries` cycles (paper §5.4: "16 entries
  per REF" for a 128 K-entry table). Avoids the cliff in DRFM rate that
  a bulk 64 ms wipe would create.
- We do **not** issue the explicit 32×(ACT + Pre+S) chain that the paper
  describes before each `DRFMab` — the DDR5-VRR DRAM model already accounts
  for the 280 ns rank-wide stall, which is the only thing a LeakyHammer
  attacker can observe. If you ever want to study the DAR-populating
  overhead itself, you'd need to inject those transactions through
  `priority_send` before the `DRFMab`.

Configured via `gem5/configs/rhsc/ramulator/dream.yaml`:

```yaml
plugins:
  - ControllerPlugin:
      impl: DREAM
      threshold: 40             # T_TH; paper uses T_RH/2 (e.g. 250 for T_RH=500)
      vertical_sharing: 1       # 1 -> gang of 32 rows, 2 -> 64, 4 -> 128, 8 -> 256
      grouping: random          # 'random' (default, paper) or 'set_assoc'
      reset_period_ns: 64000000 # tREFW
      seed: 42                  # determinism for the per-bank masks
      debug: false
      gang_size: 32             # back-compat alias; sanity-checked vs vertical_sharing
```

### 5.1.1 Implications for our LeakyHammer experiments

The previous implementation kept **independent counters per (bank, gang)**;
the rewrite makes counters **shared across all 32 banks of the
sub-channel**. Concretely, this means:

- **The attacker's gang counter is now coupled to noise from other
  banks.** Background traffic that hits *any* bank in the same rank can
  now bump the same DCT entry the receiver is watching. Expect the
  noise-vs-capacity curve for DREAM to shift downward; how much depends
  on noise-to-attacker-bank locality (the existing `dream_sender` pins
  to BG=0/Bank=0).
- **The receiver still works without modification.** It probes 1024
  rows in the *same bank*, so it doesn't self-trigger the gang counter.
  But its sensitivity is now controlled by the rank-wide ACT rate, not
  the per-bank rate. Treat the noise-rate axis on `figure7_dream.pdf`
  with appropriate suspicion until a re-run confirms the new shape.
- **`dream_th=40` is no longer a "per-bank" threshold.** Under the
  shared DCT, a uniform random ACT load will hit each counter ~32×
  faster than before. If you want to faithfully model the paper's
  T_RH=500 case, set `threshold: 250` (= T_TH = T_RH/2). The current
  `threshold: 40` is what we had been using; whether it still produces
  a useful attacker SNR under the new design is an empirical question
  that needs a re-run.

### 5.1.2 Changelog

| Date       | Change |
|------------|--------|
| (initial)  | Per-bank gang counters (`m_tusc[bank][gang]`), bulk reset every 64 ms. Deviated from the paper's cross-bank shared DCT design. |
| 2026-04-25 | Rewrote to the paper's cross-bank shared DCT with randomized grouping, vertical sharing, and gradual reset. |
| 2026-04-25 (later) | **Reverted simulator-side timing inflation introduced in commit `e462c3e`.** That commit had bumped `nDRFMab`/`nDRFMsb`/`nRFM*` in `DDR5-VRR.cpp` to 5000 mem cycles (~3 µs each) to make DRFMab events conspicuous from userspace, and inflated three companion latency-band constants in `rowhammer-side.hh` (`PERIODIC_CAP_NS` 1300→8000, `PERIODIC_CAP_NS_RFM` 550→6000, `ACCESS_CAP_NS` 250→2000) plus dropped `rowhammer-rfm-receiver.cc` `ASSERT_THRESH` from 3→1. **Side effect:** broke the RFM POC (decoded all-zeros — see `figures/figure6.broken.pdf` vs `figure6bak.pdf`) because the inflated band missed the larger-but-rarer RFM stalls. Revert restored `nDRFMab` to JEDEC formula `2*BRC*tRRFsb` (~150 ns) and the userspace bands/threshold to the artifact defaults; RFM POC now decodes `MICRO` cleanly. |
| 2026-04-26 | **"Path A" harness fix — corrected userspace ↔ Ramulator address mapping for DREAM.** Two bugs in `gem5/attack-scripts/rowhammer-addr.hh` were silently scrambling the DREAM sender's two-bank gang-collision attack: (1) `make_robaracoch` laid out bits as `[row \| bg \| ba \| rank \| col \| ch]`, but Ramulator2's `RoBaRaCoCh_with_rit` mapper reads them as `[row \| ba \| bg \| rank \| col \| ch]` — i.e. bg/ba were swapped (PRAC/RFM/noise pin (bg=7,ba=3)=`0b111,0b11` which is invariant under the swap, so they were unaffected); (2) `Addr_t` was `uint32_t`, but the DDR5_16Gb_x8 bit budget is 34 bits (TX(6)+col(6)+rank(1)+bg(3)+ba(2)+row(16)), silently dropping row bits 14–15. A related shift-truncation in `make_bits` was also fixed by casting `bits` to `T` before the shift. Companion change: `--mem-size` raised from `8GB` to `32GB` in `poc-scripts/dream_poc_utece.sh` and `result-scripts/run_config.py` (gem5 fataled when the now-correct ~10.8 GB physical address exceeded the previous 8 GB ceiling; mem-size only sets the address-space cap, doesn't change DRAM timing, so PRAC/RFM are bit-invariant). After this fix the DREAM POC and matrix run cleanly with no resyncs and no fatals. **Empirical conclusion:** see §6 — under the random-grouping plugin with `T_TH=40`, the LeakyHammer attacker recovers ~0 channel capacity (mean BER 0.47–0.48 baseline and under noise; capacity ≤ 0.15 Kbps), i.e. DREAM-C with random grouping is essentially closed against this attacker class. |
| 2026-04-26 (later) | **T_TH sweep on random grouping — full paper range.** 16 runs × 4 new T_TH values + the existing T_TH=40 baseline (full paper sweep T_RH ∈ {125, 250, 500, 1000} → T_TH ∈ {62, 125, 250, 500} plus sub-paper 40). Mean under-noise capacity drops monotonically: 0.130 (T_TH=40) → 0.032 (62, paper min) → 0.016 (125) → 0.002 (250, paper typical) → 0.001 Kbps (500, paper max). BER converges to 0.5. CSVs preserved as `results/{ber,noise_ber}_dream_t{40,62,125,250,500}.csv`; `dream.yaml` restored to `threshold: 40` for working-tree consistency. Conclusion: **no useful covert channel anywhere in the paper's T_RH range under this attacker model.** See §6.1. |

### 5.2 Sender + receiver

`rowhammer-dream-{sender,receiver}.cc` are new C++ files that mimic the
RFM sender/receiver pattern but are tuned for DREAM-C's spread-row
detection: the receiver probes 1024 rows arranged across 1024 DCT gangs
to maximise the chance of being on the same gang as a sender hammer.

`run_config.py` already wires them up:

```python
SENDER = ".../attack-binaries/dream_sender"
RECEIVER = ".../attack-binaries/dream_receiver"
```

> **Watch out:** the file `DREAM_INTEGRATION_REPORT.md` claims DREAM uses
> the `rfm_sender/rfm_receiver` binaries. **That document is stale.**
> DREAM has its own dedicated binaries — use them.

### 5.3 Receiver drift fix

Both the **DREAM** and **RFM** receivers had a per-window timing bug
(catastrophic BER on `0x55`/`0xAA` patterns; ~0% BER on `0x00`/`0xFF`).
We diagnosed and fixed it with a tightened per-window timeout
(`txn_period - 8000`) plus a phase-resync block that snaps `next_window`
forward by an integer number of periods if the receive loop overruns.

Read **`RECEIVER_DRIFT_FIX.md`** for the full root-cause analysis,
before/after BER tables, and reproduction recipe. PRAC was not affected
and was not modified.

---

## 6. Current results vs. paper

All numbers below are computed from `results/{ber,noise_ber}_*.csv` after the
2026-04-26 Path A fix (§5.1.2). "Cap" is `raw_kbps · (1 − H(BER))`, the
binary-symmetric-channel capacity used by the paper. The matrix uses the
3- or 4-rate noise subset from `run_config.py` (PRAC: 4 rates incl. one
50% BER point; RFM/DREAM: 3 rates), not the paper's full 16-rate sweep.

| Preset | Baseline raw Kbps | Baseline mean BER | Baseline cap (Kbps) | Mean cap under noise (Kbps) | Paper noiseless | Notes |
|--------|-------------------|-------------------|----------------------|------------------------------|------------------|-------|
| PRAC   | 39.02             | 0.036             | **30.36**            | 13.47                        | 39.0 Kbps        | Raw bitrate now matches paper. The 3.6% baseline BER comes entirely from `0x00` (114/800 errors); other patterns are clean. Likely receiver self-noise — out of scope for the DREAM work. |
| RFM    | 48.77             | 0.197             | 13.84                | **46.71**                    | 48.7 Kbps        | Counter-intuitive: cleaner *under* noise than at baseline. Per-pattern: BER is 0% on `0x00`, 17% on `0x55`, 12% on `0xAA`, 50% on `0xFF`. Adding noise apparently desynchronises the always-on RFM cadence enough to recover the alternating patterns. Capacity at the paper's noise rates (200/263/325) is 44.5/48.1/47.9 Kbps — i.e. the paper's claim holds in the noisy regime; the noiseless `0xFF` pathology is a known property of the post-revert detection band, not a Path-A regression. |
| DREAM  | 48.77             | **0.478**         | **0.067**            | **0.13** (T_TH=40); see sweep | (new)         | The attacker recovers essentially **no** covert channel. Per-rate: BER ≈ 0.47 across {0, 200, 263, 325}; capacity ≤ 0.15 Kbps everywhere. ~360× less leaky than RFM under noise, ~100× less than PRAC. See **§6.1 T_TH sweep** for paper-faithful settings. |

**Why DREAM looks closed (mechanistic story consistent with the data):**

1. The plugin is now paper-faithful (per-bank random XOR masks, shared
   sub-channel DCT, `T_TH=40`, `vertical_sharing=1`). Each bank's masks
   are independent, so the sender's two-bank gang-collision strategy
   (hammer two banks whose `(row XOR mask[ba])` lands on the same DCT
   entry) produces a well-defined attack — but only against *that* one
   gang, while the receiver still has to land its 1024-row probe set on
   that same gang.
2. With shared-DCT semantics the receiver's own probes and any noise
   contribute to whatever counter the sender is trying to saturate, but
   with the random per-bank mask their contributions land on **different**
   DCT entries from the sender's. Net: the sender hammers gang `g`, the
   receiver mostly probes other gangs, and even when probes do land on
   `g` the rate-of-arrival of DRFMab is too low for the receiver's
   per-window classifier to outvote noise on every pattern.
3. Post-`e462c3e`-revert, DRFMab's controller-side stall is in the same
   ~250–550 ns band as RFM. The DREAM receiver's spike classifier can
   *count* spikes in that band but cannot tell DRFMab apart from a
   merely-busy queue, so any non-DRFMab queue noise feeds straight into
   the bit decision.

The empirical 0.13 Kbps under noise is consistent with "the sender's
intended modulation is invisible at the receiver's bank/gang slice."

### 6.1 T_TH sweep (random grouping) — full paper range

To rule out "T_TH=40 is a single-config artefact," the full DREAM matrix
was re-run at every T_TH the paper studies (T_RH ∈ {125, 250, 500, 1000}
→ T_TH ∈ {62, 125, 250, 500}) on 2026-04-26/27 (random grouping,
`vertical_sharing=1`, `seed=42`, all other config identical). The
sub-paper T_TH=40 case is included for reference. Snapshots live in
`results/ber_dream_t{40,62,125,250,500}.csv` and
`results/noise_ber_dream_t{40,62,125,250,500}.csv`.

| T_TH | T_RH eq. | raw Kbps | base BER | base Cap | r=200 BER | r=200 Cap | r=263 BER | r=263 Cap | r=325 BER | r=325 Cap | mean noise Cap |
|------|----------|----------|----------|----------|-----------|-----------|-----------|-----------|-----------|-----------|-----------------|
| 40   | 80 (sub-paper) | 48.77 | 0.4781 | 0.067 | 0.4684 | 0.140 | 0.4675 | 0.149 | 0.4731 | 0.102 | **0.130** |
| 62   | 125 (paper min) | 48.77 | 0.4872 | 0.023 | 0.4844 | 0.034 | 0.4841 | 0.036 | 0.4863 | 0.027 | **0.032** |
| 125  | 250 | 48.77 | 0.4938 | 0.006 | 0.4884 | 0.019 | 0.4881 | 0.020 | 0.4922 | 0.009 | **0.016** |
| 250  | 500 (paper typical) | 48.77 | 0.4972 | 0.001 | 0.4950 | 0.004 | 0.4956 | 0.003 | 0.4972 | 0.001 | **0.002** |
| 500  | 1000 (paper max) | 48.77 | 0.4975 | 0.001 | 0.4966 | 0.002 | 0.4969 | 0.001 | 0.4988 | 0.0002 | **0.001** |

(Capacities in Kbps, computed as `raw_kbps · (1 − H(BER))`.)

**Observations:**

1. **Capacity is monotone non-increasing in T_TH** at every noise rate
   and at baseline — exactly as the mechanistic story predicts (lower
   T_TH ⇒ DRFMab fires more often per attacker hammer ⇒ more signal at
   the receiver). The full sweep covers the paper's entire T_RH range
   {125, 250, 500, 1000}; capacity collapses by ~130× from T_TH=40 to
   T_TH=500.
2. **BER converges to 0.5 (random guessing) as T_TH grows**:
   0.478 → 0.487 → 0.494 → 0.497 → 0.498. The LeakyHammer decoder is
   not extracting any non-trivial signal at paper-faithful settings.
3. **Across every paper-faithful T_TH ∈ {62, 125, 250, 500} the mean
   under-noise capacity is ≤ 0.04 Kbps**, dropping to ~0.001 Kbps at
   the paper's most defender-friendly T_TH=500 — i.e. ≥ 1000× below RFM
   (46.7 Kbps) and ≥ 300× below PRAC (13.5 Kbps) at the same noise
   rates. This holds the attacker model fixed and varies only the
   defense parameter, so the gap is attributable to DREAM-C with
   random grouping itself.

**Conclusion:** Under the LeakyHammer attacker class implemented here
(two-bank gang-collision sender + 1024-row spread-row receiver +
per-window latency-band classifier), DREAM-C with random grouping
*provides no usable covert channel anywhere in the paper's T_RH ∈
{125, 250, 500, 1000} range*. The remaining unsettled questions
(set-assoc grouping as a positive control, smarter rank-scope decoders)
are separate research directions; they do not change this conclusion
within the stated attacker model.

> **Important caveat:** "no significant covert channel" is a claim
> about *this attacker class*, not about DREAM-C in general. A smarter
> attacker (rank-scope multi-bank-group probing, spike-timing
> cross-correlation against a known sender clock, or a per-bank
> mask-recovery side-channel that breaks the random grouping) could in
> principle recover a channel. The data here closes the question
> "does the LeakyHammer paper's attack work against DREAM-C random
> grouping?" but not "is DREAM-C random grouping universally secure?".

Figures live in `gem5/figures/`:
- `figure4.pdf` — PRAC channel capacity vs noise intensity (current).
- `figure6.pdf` — RFM POC (current; matches `figure6bak.pdf` at the bit level, per-window RFM counts differ — Debug-build artifact, see §4.2).
- `figure6.broken.pdf` — RFM POC against the inflated-timing state, all-zero decode (kept for reference).
- `figure6bak.pdf` — pre-`e462c3e` working RFM POC reference (Apr 3, original Release `libramulator.so`).
- `figure6_dream.pdf` — DREAM POC sanity figure (**new 2026-04-27**), same
  layout as `figure6.pdf` but for the DREAM POC log
  (`results/dream/poc/dream_poc_utece.txt`). The y-axis is per-window
  spike count (not RFM count), the background shading is the sent bit,
  red `x` marks each bit error, and the bottom annotation reports
  `Sent: 'UTECE'  Decoded: 'd??&L'  Errors: 18/40 (45.0% BER)`. Side-by-side
  with `figure6.pdf` this is the visual companion to §6.1: under random
  grouping the spike-count signal is decorrelated from the sent bit and
  the decoder collapses to ~50% BER. Regenerate with:
  ```bash
  cd gem5 && uv run --with pandas --with matplotlib python3 \
    plot-scripts/figure6_dream_plotter.py \
    results/dream/poc/dream_poc_utece.txt figures/figure6_dream.pdf
  ```
- `figure7.pdf` — RFM channel capacity vs noise intensity.
- `figure7_dream.pdf` — DREAM, same axes as figure7 (**regenerated 2026-04-26**, shows ~0 capacity at all noise rates — visually almost a flat line at the bottom of the plot).

---

## 7. What I'm currently working on

**Goal:** Get clean, paper-comparable LeakyHammer covert-channel results
for **DREAM-C**, alongside the original PRAC/RFM, so we can argue about
whether DREAM is more or less leaky than the industry-standard defenses.

**Done:**
- Ported DREAM-C to Ramulator2 as a plugin.
- Wrote DREAM-specific sender/receiver attack binaries.
- Wired DREAM into the LeakyHammer experiment harness (configs, run_config, plotters).
- Diagnosed and fixed a long-standing receiver phase-drift bug that broke
  alternating-bit patterns (`0x55`/`0xAA`) for both DREAM and RFM.
  See `RECEIVER_DRIFT_FIX.md`.
- Reproduced the paper's RFM noiseless raw bitrate (48.77 vs 48.7 Kbps);
  capacity matches at the paper's noise rates (~46.7 Kbps mean).
- **2026-04-26 — Path A harness fix.** Diagnosed and corrected a
  userspace ↔ Ramulator address mapping mismatch (`bg/ba` swap +
  `Addr_t=uint32_t` truncating row bits 14–15) and the companion
  `--mem-size` ceiling, then re-ran the full DREAM matrix. See §5.1.2
  changelog and §6 for the empirical results.
- **Headline finding for DREAM-C with random grouping (`grouping=random`,
  `vertical_sharing=1`):** the LeakyHammer attacker recovers ≤ 0.15 Kbps
  at T_TH=40 and **monotonically less** at every paper-faithful
  setting (T_TH ∈ {62, 125, 250, 500} → mean noise capacity 0.032 /
  0.016 / 0.002 / 0.001 Kbps). BER converges to 0.5 (random) as T_TH
  grows. **No useful covert channel under this attacker model anywhere
  in the paper's T_RH ∈ {125, 250, 500, 1000} range.** Comparison: RFM
  46.7 Kbps, PRAC 13.5 Kbps at the same noise rates. See **§6.1 T_TH
  sweep** for the per-rate table.
- **2026-04-26/27 — full paper-range T_TH sweep on random grouping
  completed.** Snapshots in `results/{ber,noise_ber}_dream_t{40,62,125,250,500}.csv`.
  Working-tree `dream.yaml` left at `threshold: 40` (historical default)
  and `results/{ber,noise_ber}_dream.csv` are the T_TH=40 data, so
  anything reading the un-suffixed CSVs gets internally consistent state.

**Open / likely next steps (none required to ship the DREAM result):**
1. **(Positive control, recommended before claiming "DREAM closes the
   channel")** Run DREAM with `grouping: set_assoc` for a point of
   comparison. The DREAM paper itself argues set-assoc grouping under
   MOP4 mapping produces hot counters and a usable channel; observing
   a non-zero capacity there would (a) prove the harness is in fact
   capable of detecting a DREAM channel when one exists, and (b) rule
   out the alternative explanation "DREAM-random looks closed because
   the harness/decoder is broken, not because DREAM-random is closed."
   This is the **only experiment left that could meaningfully change
   the wrap-up story**.
2. **(Better attacker, research-extension)** The current decoder uses a
   per-window spike-count threshold against latencies in `(250, 1300)` ns.
   A smarter attacker could (i) probe two different bank-groups and
   require *simultaneous* spikes (DRFMab is rank-scope, RFM is
   bank-scope) or (ii) cross-correlate spike timing against the
   sender's clock. If either recovers a meaningful channel, the wrap-up
   claim becomes "DREAM-C with random grouping resists the *paper's*
   attacker but not all attackers" rather than "no significant covert
   channel." Out of scope for the present project.
3. **(Polish, optional)** Investigate the PRAC noiseless `0x00` BER
   (114/800 errors, 14.25%; other patterns are clean). Looks like
   receiver self-noise inside `prac_receive`. Independent of the DREAM
   work.
4. **(Polish, optional)** Run `setup_recommended_subset.py` instead of
   `setup_test.py` to do the full paper-style 16-rate noise sweep (we
   currently use a 3- or 4-rate subset to keep wall time down). Mostly
   relevant for figure aesthetics.
5. **(Polish, optional)** Sweep `vertical_sharing ∈ {2, 4, 8}` to check
   the effect of larger gangs (256-row gang at vs=8 means each DRFMab
   covers more rows but fires less often — net effect on attacker SNR
   is unclear without measurement). Not expected to *increase* capacity
   relative to vs=1 since the per-bank XOR mask still shuffles the
   target gang, but worth a single matrix run to confirm.

---

## 8. Important quirks and gotchas

- **Use Docker, not Podman.** Earlier sessions tried podman by mistake and
  it broke ownership on result files. The image name is
  `leakyhammer_artifact:latest`, loaded from `leakyhammer_artifact.tar`.
- **Cap parallelism at 4.** Each docker container peaks at ~3 GB RSS. The
  paper authors used 16 on a slurm cluster; on a single dev box that
  OOM-kills the host.
- **Files written by gem5 inside docker are owned by uid 1000.** If you
  see permission errors writing CSVs/PDFs, the cause is almost always
  stale root-owned files from an earlier (mis-launched) docker run. Fix:
  ```bash
  docker run --rm -v "$PWD/gem5":/app leakyhammer_artifact \
      "chown -R 1000:1000 /app/results /app/figures"
  ```
- **`pd.read_csv` on the BER CSVs needs `dtype={'sent': str, 'received': str}`**
  because the columns are 800-character binary strings that overflow when
  pandas tries to convert them to floats. The repo's `parse_and_print.py`
  and figure plotters already do this; if you write a new analysis
  script, do it too.
- **`DREAM_INTEGRATION_REPORT.md` is outdated.** It claims DREAM uses RFM's
  sender/receiver binaries — wrong. Use `RECEIVER_DRIFT_FIX.md` and this
  file as the sources of truth.
- **`compile-scripts/recompile_*.sh` only rebuild attack binaries, not the
  Ramulator plugin.** If you edited a `.cpp` under
  `gem5/ext/ramulator2/` (e.g. `dream.cpp`, `DDR5-VRR.cpp`), you must run
  `./rebuild.sh --ramulator` to relink `libramulator.so`. `gem5.opt` does
  *not* need to be rebuilt for internal Ramulator changes — it dynamically
  links the `.so` via `RPATH`. Use `--all` only when changing Ramulator's
  public ABI or a header gem5 itself includes. See §4.2.
  Symptom of running with a stale `.so`: result CSVs come out *bit-identical*
  to a previous run despite source changes.
- **`txt.txt` at the repo root is from a very old run.** Ignore it.
  Always read the latest data from `gem5/results/*.csv` and the latest
  figures from `gem5/figures/`.
- **Per-experiment receiver logs include diagnostic lines:**
  ```
  [RECV] MinSleepAssert: 5692         <-- positive == healthy
  [RECV] Resyncs: 0 (0 bits skipped)  <-- 0 == clean run
  ```
  If `MinSleepAssert` goes negative or `Resyncs` > 0 on any run, the
  drift fix isn't holding — investigate before trusting the resulting BER.

---

## 9. Quick reference — common one-liners

```bash
# Rebuild Ramulator only (after editing any .cpp under ext/ramulator2/)
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/gem5":/app leakyhammer_artifact \
    "./rebuild.sh --ramulator"

# Recompile DREAM attack binaries only (after editing dream-*.cc in attack-scripts/)
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/gem5":/app leakyhammer_artifact \
    "./compile-scripts/recompile_dream.sh"

# Regenerate run_scripts/ + run.sh
cd gem5 && uv run python3 ./result-scripts/setup_test.py -c -cc docker

# Run the whole matrix, 4 in parallel
cat gem5/run.sh | sed 's/^sh //' | xargs -I{} -P4 sh {}

# Re-parse results into CSVs and rebuild figures
uv run --with pandas --with numpy --with matplotlib --with seaborn \
    python3 gem5/result-scripts/parse_and_print.py

# Inspect one result
less gem5/results/dream/baseline/t20000_100b_p0x55_r0d_dream.txt

# Sanity-check that DREAM/RFM receivers aren't drifting
grep -E "MinSleepAssert|Resyncs" gem5/results/{rfm,dream}/baseline/*.txt
```

---

## 10. References

- `LeakyHammer.pdf` — the source paper.
- `DREAM.pdf` — the DREAM-C paper we ported into the harness.
- `RECEIVER_DRIFT_FIX.md` — full writeup of the receiver phase-drift bug,
  the fix, and before/after numbers.
- `README.md` — the artifact authors' original README. Useful for the
  Slurm-based execution path; locally we use the simpler `xargs -P4`
  recipe in §4.4 above.
