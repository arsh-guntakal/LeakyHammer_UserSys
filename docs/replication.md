# Replicating the report

This repository is meant as a clean baseline: it reproduces the results in the
report as closely as the evidence allows, **including the parts that look
broken**, so that later changes can be measured against it. Nothing here was
tuned to hit a number. Where a number does not reproduce, this page says so and
lists what was tried.

```bash
tools/build                  # once

# The guest program directory must have this exact 45-character length (see
# "Conditions that change the result"); a symlink to the built programs will do.
GUEST_DIR=/tmp/leakyhammer-reproduction/attack-binaries
mkdir -p "$(dirname "$GUEST_DIR")" && ln -sfn "$PWD/build/attack-binaries" "$GUEST_DIR"
export LEAKYHAMMER_GUEST_BIN_DIR="$GUEST_DIR"

PY=.venv/bin/python
$PY -m leakyhammer.experiments.poc.run --config default --batch report
$PY -m leakyhammer.experiments.poc.plot --config default --batch report
$PY -m leakyhammer.experiments.noise_sweep.run --config report --batch report -j 34
$PY -m leakyhammer.experiments.noise_sweep.plot --config report --batch report
```

This runs the four proofs of concept and the 68-run `report` sweep (7 minutes
and 3 GB per simulation, about an hour at `-j 34`) and prints Table 1.

## Result

| | Report | Replicated | Verdict |
|---|---|---|---|
| **PRAC** raw rate / baseline BER / baseline capacity / noise capacity | 39.02 / 0.036 / 30.36 / 13.47 | 39.02 / 0.0356 / 30.359 / 13.472 | exact |
| **RFM** baseline BER / baseline capacity | 0.000 / 48.77 | 0.0000 / 48.769 | exact (from the legacy variant) |
| **RFM** noise capacity | 46.71 | 46.63 | close (0.2% low) |
| **DREAM-C** (T_TH=40) baseline BER / baseline cap / noise cap | 0.478 / 0.067 / 0.130 | 0.248 / 9.19 / 8.56 | **differs on purpose**: the report's attack was defective (below) |
| **RRS** raw / baseline BER / baseline cap / noise cap | 46.12 / 0.42 / 0.85 / 0.91 | 46.01 (46.19 noisy) / 0.431 / 0.635 / 0.738 | approximate, not exact |
| POC, PRAC and RFM | `MICRO`, 0/40 | `MICRO`, 0/40 | exact |
| POC, DREAM-C | `d??&L`, 18/40 | `TTE??`, 7/40 | **differs on purpose** |
| POC, RRS | `HT STX STX @ @`, 14/40 | `??? ?`, 16/40 | **not reproduced** |

PRAC and RFM still match the report. DREAM-C and RRS do not support the
report's conclusions as written; see the next section.

## Where the report and the repository disagree

- **DREAM-C is not closed.** The report's attack never activated the sender's
  rows, started its receiver ~31 windows late, and could not tell refresh from a
  defense stall. With those fixed (`attacks/dream/`) the same plugin leaks about
  9 Kbps at T_TH=40 and falls to near zero by T_TH=500 (table in
  [dream-c.md](dream-c.md)). The old numbers are reproducible at commit `bad71a9`.
- **RRS is inconclusive.** The report's RRS rows are kept as they were, but
  `latency_histogram` finds no excess of slow probes in windows of 1, so it is
  unknown whether the channel is closed or the attack does not trigger swaps
  ([attack-validity.md](attack-validity.md)).
- **Units.** "Kbps" in the code is bits/s divided by 1024; the report's figures
  use 1000, so its 50 Kbps is about 48.8 here.

## Where each number came from

The report's Table 1 was not measured from one version of the code. Following
the git history, each row comes from a different state:

| Report cell | Code that produced it | In this repo |
|---|---|---|
| PRAC row, RFM noise, DREAM-C row, POCs for PRAC, RFM, DREAM-C | `6d7719a`, the main line when the DREAM-C work was finished | `attacks/{prac,rfm,dream}`, the `prac`, `rfm`, `dream` defenses |
| **RFM baseline** (BER 0.000, 48.77 Kbps) | `2b847b2`, **before** a revert that was made because it broke the RFM proof of concept | the `rfm_prerevert` defense |
| RRS row and POC | the `row-swap` branch tip, `7ff033e` | `attacks/rrs`, the `rrs` defense |

**RFM baseline.** That commit forced every RFM stall to 5000 memory cycles,
widened the receivers' latency bands (8000/6000/2000 ns instead of 1300/550/250),
and lowered the RFM receiver's decision threshold from 3 to 1. With those, all
four data patterns decode with no errors (BER 0.000, 48.774 Kbps), and the
simulation's `MinSleepAssert: 5692` matches the old notes. The project's own notes
record that state decoding the RFM proof of concept as all zeros (not re-measured
here), which is why it was reverted; the report's RFM proof of concept (`MICRO`)
therefore comes from the later code, while its RFM baseline comes from the earlier. `rfm_prerevert` reproduces that earlier state:
its programs are kept verbatim in `attacks/legacy/rfm_prerevert/` (the files are
byte-for-byte what the commit had), and its timings are five `timing:` overrides
in `rfm_prerevert.yaml`. The overrides were checked against the original code:
the same four runs match to the nanosecond. The `report` config takes RFM's
baseline from `rfm_prerevert` and its noise rows from `rfm`.

## Conditions that change the result

The simulation is deterministic, but it is sensitive to the guest's memory
layout, so these were pinned (`docs/experiments.md#reproducibility` has the
mechanism): the attack programs are built with the system `g++` 9.4 and the
original artifact's embedded source names, and the guest is started with a
45-character program directory (`/tmp/leakyhammer-reproduction/attack-binaries`,
set with `LEAKYHAMMER_GUEST_BIN_DIR` as above). That length is the one the
pre-reorganization measurements used; it gave the closest match. Without it
(`--config default`, relative paths) the same code gives slightly different
numbers, for example DREAM-C's noise capacity of 0.110 instead of 0.131 Kbps.
Every result records the guest command it was measured with.

## What does not reproduce exactly, and what was tried

**DREAM-C and RFM noise: a few bits off.** The original notes recorded DREAM-C's
baseline as 1530 bit errors (of 3200); this gives 1529. Tried, all on the DREAM-C
baseline: the original container's program path `/app/attack-binaries/...`
(1524), the 45-character path (1529), the relative default (1536), running from
`/app` as the container did (1524, no effect), and a Release instead of Debug
Ramulator (1529, identical per pattern). None reaches 1530, so some original
input is unrecovered. Capacity near BER 0.5 is very sensitive to a few bits, so
0.069 against 0.067 is the same measurement, not a different result.

**RRS: close, not exact.** The report's RRS numbers (raw 46.12 Kbps, BER 0.42,
capacity 0.85 and 0.91) are matched in raw rate and roughly in BER, not in
capacity, and its proof of concept decodes 14 of 40 bits wrong where this gets 16.
The report's received bits, `HT STX STX @ @`, were never produced. Tried:

- **Threshold.** The report says N_TH=40, but 40 gives a raw rate of 44.05 Kbps
  and BER 0.27 (default guest path), nothing like its table; 50, the committed value in `rrs.yaml`,
  matches its raw rate. The numbers appear to come from 50.
- **Which commit's programs** (`49b72cb`, `51c9ce6`, `7ff033e`): they differ in
  layout and give baseline BER 0.433, 0.432, 0.431 and noise capacity 0.805,
  0.799, 0.738.
- **Guest path, full matrix:** both authors' recorded directories under
  `/home/...`, the 45-character one and the relative default give baseline BER
  0.431 to 0.435 and noise capacity 0.715 to 0.738.
- **Guest path and `--mem-size`, proof of concept:** the container's
  `/app/attack-binaries`, the `./attack-binaries` form the original POC script
  used, and the relative default, each at 8 GB and 32 GB: the bits are identical
  in all six, so neither is the cause. (The container's path was not run on the
  full RRS matrix.)

The report also describes a receiver calibrated to a 400-500 ns swap spike, but
every committed version uses a 3000 ns band (marked TODO) with a 500 ns timeout
margin and no resynchronization. Its RRS numbers most likely came from an
uncommitted local change that history cannot recover. Searching settings until the
report's bits appeared would be fitting, not replicating, so this is left open.

## For the next change

Everything that makes these numbers questionable is isolated, so it can be fixed
and measured against this baseline:

- `attacks/legacy/rfm_prerevert/`, `rfm_prerevert.yaml` and the `report` config's
  `rfm_prerevert` entry reproduce an RFM known to be unrealistic. Delete them when
  the report's RFM baseline is redone with the real RFM.
- The RRS receiver's band, margin and threshold (`attacks/rrs/`, `rrs.yaml`).
- The pinned guest directory exists only to match old numbers.
