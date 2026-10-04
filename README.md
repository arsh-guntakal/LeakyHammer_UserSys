# LeakyHammer + DREAM-C + RRS

Covert channels against RowHammer defenses, simulated on gem5 + Ramulator2.
This repository extends the artifact of the MICRO 2025 paper
[*Understanding and Mitigating Covert and Side Channel Vulnerabilities
Introduced by RowHammer Defenses*](https://arxiv.org/abs/2503.17891)
(original README: [ARTIFACT_README.md](ARTIFACT_README.md)) to ask whether two
newer defenses, **DREAM-C** and **RRS**, are as leaky as the standardized PRAC
and RFM. The write-up is in `base-project-report.pdf` (not tracked).

| Defense | Ramulator2 plugin | Attack programs |
|---|---|---|
| PRAC, RFM | original artifact | `src/leakyhammer/attacks/{prac,rfm}/` |
| DREAM-C | `dream.cpp` (ours) | `src/leakyhammer/attacks/dream/` |
| RRS | `rrs.cpp` (original artifact) | `src/leakyhammer/attacks/rrs/` |

## Layout

```
src/leakyhammer/        importable core (Python 3.8)
    defenses.py           the defense registry: one entry per defense
    sim.py                builds and runs gem5 commands
    metrics.py            log parsing, BER, capacity
    results.py            result store (results/<experiment>/<batch>/<trial>/)
    attacks/              guest-side C++ (per defense) + build.py
    plotting/             one function per figure
    experiments/          noise_sweep, poc, latency_profile (main / run / plot)
tests/                  unit tests; tests/experiments/ for the experiments
tools/                  build, lint, gem5-diff
docs/                   how-tos and the historical project notes
gem5/                   vendored gem5 24.0 + Ramulator2 (see gem5/PATCHES.md)
```

First-party code is in `src/`; the simulator is a vendored dependency whose
changes are listed in [gem5/PATCHES.md](gem5/PATCHES.md).

## Setup

The project runs inside its container (Ubuntu 20.04, Python 3.8, g++ 9 and 10).

```bash
docker build -t leakyhammer .
# Mount the repo so edits and results persist. The mount hides the image's
# .venv, so recreate it once with `uv sync --frozen`.
docker run --rm -it -v "$PWD":/app/LeakyHammer_UserSys leakyhammer bash
cd /app/LeakyHammer_UserSys && uv sync --frozen
```

Everything below runs inside the container from the repository root.

> Keep the uv venv off `PATH` when building gem5: gem5 embeds the *system*
> Python, and mixing the two aborts with `No module named '_contextvars'`.
> `tools/build` handles this. The Python tools do want the venv: use
> `uv run python -m ...` or `.venv/bin/python -m ...`.

## Build (once, and after C++ changes)

```bash
JOBS=32 tools/build              # Ramulator2 + gem5 + attack programs
tools/build --attacks            # only the attack programs (seconds)
tools/build --ramulator          # after editing a Ramulator plugin
```

The gem5 link takes tens of minutes. `tools/build` stops on any failure.

## Reproduce the results

```bash
# Proof of concept: send a short message through each defense (~1 minute).
.venv/bin/python -m leakyhammer.experiments.poc.run

# Full BER/capacity sweep: 68 simulations, ~7 minutes each, 3 GB RAM each.
.venv/bin/python -m leakyhammer.experiments.noise_sweep.run --config default -j 32
.venv/bin/python -m leakyhammer.experiments.noise_sweep.plot --config default
```

Expected proof-of-concept results (the simulation is deterministic, so these
repeat exactly):

| Defense | Sent | Decoded | Bit errors |
|---|---|---|---|
| PRAC, RFM | `MICRO` | `MICRO` | 0 / 40 |
| DREAM-C | `UTECE` | `d??&L` | 18 / 40 |
| RRS | `MICRO` | `??? ?` | 16 / 40 |

Other configs: `quick` (17 runs), `dream_threshold` (the T_TH sweep),
`rrs_threshold`. Add `--dry-run` to print one shell command per trial for your
own scheduler. Results go to `results/`; see [docs/experiments.md](docs/experiments.md).

## Tests and lint

```bash
uv run pytest -m "not slow"        # unit tests, seconds, no simulator needed
uv run pytest -m integration       # real DREAM/RFM POCs; needs tools/build first
tools/lint
```

## Extending

- A new defense: [docs/adding-a-defense.md](docs/adding-a-defense.md).
- A new experiment, config format, result layout: [docs/experiments.md](docs/experiments.md).
- Conventions and what to test: [CLAUDE.md](CLAUDE.md).
- DREAM-C design notes and the original result tables:
  [docs/dream-history.md](docs/dream-history.md) (historical; paths are stale).

Results are deterministic but depend on the guest's memory layout, so three
things you would not expect to matter do: the attack programs' compiler (plain
`g++` 9.4, not the container's `CXX=g++-10`), the source paths embedded in
them, and the strings on the simulated stack (the program path and the noise
period). The build and `sim.py` fix all three; see
[docs/experiments.md](docs/experiments.md#reproducibility) before changing
either. A crashed simulation is recorded as failed and never averaged in.

## Results

The full 68-run matrix (`--config default`) next to the report's Table 1.
Capacity is `raw * (1 - H(mean BER))`; "noise" is the mean over the noise rates.
*Default* is what you get from a fresh clone; *pinned* reproduces, bit for bit,
the measurements made before this repository was reorganized (see
[docs/experiments.md](docs/experiments.md#reproducibility)).

| Defense | Raw Kbps | Baseline BER | Baseline cap (Kbps) | Mean noise cap (Kbps) |
|---|---|---|---|---|
| | report / default | report / default / pinned | report / default / pinned | report / default / pinned |
| PRAC | 39.02 / 39.02 | 0.036 / 0.036 / 0.036 | 30.36 / 30.36 / 30.36 | 13.47 / 13.47 / 13.47 |
| RFM | 48.77 / 48.77 | 0.000 / 0.178 / 0.187 | 48.77 / 15.87 / 14.88 | 46.71 / 46.95 / 46.63 |
| DREAM-C (T_TH=40) | 48.77 / 48.77 | 0.478 / 0.480 / 0.478 | 0.067 / 0.056 / 0.069 | 0.130 / 0.110 / 0.131 |
| RRS | 46.12 / 46.1 | 0.42 / 0.432 / 0.431 | 0.85 / 0.619 / 0.635 | 0.91 / 0.737 / 0.738 |

- **PRAC and DREAM-C reproduce the report** (PRAC exactly). Both conclusions
  hold in every mode: DREAM-C's channel is closed (capacity ~0.1 Kbps, BER ~0.48).
- **RFM's noise capacity matches; its baseline does not.** The report lists
  baseline BER 0.000; this code gives 0.18 (0% on `0x00`, 13-15% on `0x55`/`0xAA`,
  43-49% on `0xFF`, depending on the guest-path mode). The project's own earlier notes recorded 0.197, so the
  report's 0.000 looks wrong or came from a different build. Unexplained.
- **RRS is close but not the report's numbers.** The report describes a receiver
  calibrated to a 400-500 ns swap spike and N_TH=40; the code ships a
  `RRS_SWAP_CAP_NS = 3000` band marked TODO, a threshold of 50 in `rrs.yaml`,
  and no drift fix in the RRS receiver. Exact RRS replication is open work.
- The DREAM-C T_TH sweep (62/125/250/500) is the `dream_threshold` config
  (80 runs). Its results are in the historical notes
  ([docs/dream-history.md](docs/dream-history.md), section 6.1) and have not been
  re-run since the reorganization.

## What was verified

The reorganization was checked against the pre-reorganization results:
all 68 trials of the pinned matrix match the earlier measurements exactly (sent
and received bits, time, error count), and the generated CSVs are
byte-identical to the original harness's. The unit tests (`pytest -m "not
slow"`) and the two integration tests pass; the DREAM and RFM POCs, the full
matrix, the plotting path and the build all ran in the project container.
**Not** verified: building the image from the `Dockerfile`, the `docker run`
mount flow above, the Slurm path (use `--dry-run` to emit per-trial commands),
the `latency` and `poc_prac` figures against the original plotters' output
(they run on real logs, but only the other five plotters were compared
byte for byte), and the website-fingerprinting experiments of the original
artifact (not part of this repository's scripts).
