# LeakyHammer + DREAM-C + RRS

Covert channels against RowHammer defenses, simulated on gem5 + Ramulator2.
This repository extends the artifact of the MICRO 2025 paper
[*Understanding and Mitigating Covert and Side Channel Vulnerabilities
Introduced by RowHammer Defenses*](https://arxiv.org/abs/2503.17891)
([original artifact](https://github.com/CMU-SAFARI/LeakyHammer)) to ask whether two
newer defenses, **DREAM-C** and **RRS**, are as leaky as the standardized PRAC
and RFM. The course report that accompanies this work is not part of the repository.

| Defense | Ramulator2 plugin | Attack programs |
|---|---|---|
| PRAC, RFM | original artifact | `src/leakyhammer/attacks/{prac,rfm}/` |
| DREAM-C | `dream.cpp` (ours) | `src/leakyhammer/attacks/dream/` |
| RRS | `rrs.cpp` (original artifact) | `src/leakyhammer/attacks/rrs/` |

## Layout

```
gem5/                   code that must be integrated inside the simulator
src/leakyhammer/        importable Python + the C++ programs run on the simulator
    defenses.py, sim.py, metrics.py, results.py, config.py   (the core library)
    attacks/              guest-side C++ per defense, and the code that builds it
    experiments/<name>/   programs that produce results (see below)
tests/                  unit, integration and experiment tiers
tools/                  build, compile-attacks, lint, gem5-diff
docs/                   how-tos and the historical project notes
```

Future contributors should follow this structure:

- **`gem5/`**: code that must be integrated *inside the simulator* (vendored
  gem5 24.0 + Ramulator2; see [gem5/PATCHES.md](gem5/PATCHES.md)). Programs that
  run *on* the simulator do not go here.
- **`src/leakyhammer/`**: importable Python and the non-importable C++ programs
  that run on the simulator. By itself it has no `main` functions and produces
  no results or figures. It holds the utilities for driving gem5: building,
  running, and reading stats.
- **`src/leakyhammer/experiments/`**: programs that *produce results*. Each
  experiment `<foo>/` has:
  - `README.md`: how to run it and what data it provides;
  - `main.py`: generates a *single* artifact;
  - `configs/<config>.yaml`: describes a *sweep* of artifacts;
  - `run.py`: generates the sweep; `--config` is required;
  - `plot.py`: draws the figures for a sweep; `--config` is required.
- **`tests/`**: divided into `unit` (fast, no simulator), `integration` (core
  library against a real gem5) and `experiment` (an experiment end to end)
  tiers. See [tests/README.md](tests/README.md).

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

## Reproduce the report

```bash
tools/replicate-report            # JOBS=34 for a big machine; about an hour
```

This reruns the report's measurements (the four proofs of concept and the 68-run
sweep behind its Table 1) under the conditions that best reproduce its numbers,
and prints the table. [docs/replication.md](docs/replication.md) maps every
reported number to the code that produced it, how close this comes, and what was
tried where it doesn't match.

To run the experiments on their own:

```bash
.venv/bin/python -m leakyhammer.experiments.poc.run --config default
.venv/bin/python -m leakyhammer.experiments.poc.plot --config default
.venv/bin/python -m leakyhammer.experiments.noise_sweep.run --config default -j 32
.venv/bin/python -m leakyhammer.experiments.noise_sweep.plot --config default
```

Other sweep configs: `quick` (17 runs), `dream_threshold`, `rrs_threshold`. Add
`--dry-run` to print one shell command per trial for your own scheduler. Results go
to `results/`. Each experiment's README (`src/leakyhammer/experiments/<name>/README.md`)
says how to run it and what it measures; [docs/experiments.md](docs/experiments.md)
describes the shared record format.

## Tests and lint

```bash
uv run pytest                      # everything; tiers that need gem5 skip if it is not built
uv run pytest -m "not slow"        # unit tests only: seconds, no simulator needed
uv run pytest -m "integration or experiment"   # real simulations; needs tools/build first
tools/lint
```

## Extending

- A new defense: [docs/adding-a-defense.md](docs/adding-a-defense.md).
- A new experiment, config format, result layout: [docs/experiments.md](docs/experiments.md).
- Conventions and what to test: [CLAUDE.md](CLAUDE.md).
- How DREAM-C is modeled and attacked, its results, and open questions:
  [docs/dream-c.md](docs/dream-c.md).

Results are deterministic but depend on the guest's memory layout, so three
things you would not expect to matter do: the attack programs' compiler (plain
`g++` 9.4, not the container's `CXX=g++-10`), the source paths embedded in
them, and the strings on the simulated stack (the program path and the noise
period). The build and `sim.py` fix all three; see
[docs/experiments.md](docs/experiments.md#reproducibility) before changing
either. A crashed simulation is recorded as failed and never averaged in.

## Results

`tools/replicate-report` next to the report's Table 1. Capacity is
`raw * (1 - H(mean BER))`; "noise" is the mean over the noise rates.

| Defense | Baseline BER | Baseline cap (Kbps) | Noise cap (Kbps) | Verdict |
|---|---|---|---|---|
| PRAC | 0.036 / 0.0356 | 30.36 / 30.36 | 13.47 / 13.47 | exact |
| RFM | 0.000 / 0.0000 | 48.77 / 48.77 | 46.71 / 46.63 | baseline exact; noise within 0.2% |
| DREAM-C (T_TH=40) | 0.478 / 0.4778 | 0.067 / 0.069 | 0.130 / 0.131 | close (1529 vs 1530 bit errors) |
| RRS | 0.42 / 0.431 | 0.85 / 0.635 | 0.91 / 0.738 | approximate |

Each cell is *report / replicated*. The proofs of concept reproduce exactly for
PRAC, RFM and DREAM-C (`MICRO`, `MICRO`, `d??&L` at 18/40); RRS gets 16/40 where
the report has 14/40. The report's RFM baseline comes from an older code state
that was later reverted as broken (kept here as `rfm_prerevert`), and its RRS
numbers could not be recovered from history; both are explained in
[docs/replication.md](docs/replication.md). The DREAM-C T_TH sweep is the
`dream_threshold` config; its earlier results are in [docs/dream-c.md](docs/dream-c.md)
and were not re-run.

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
