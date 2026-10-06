# Style guide

This file tells contributors (human or Claude) how to write code that looks
like it belongs here. This is a research project: results must be
reproducible, so correctness and tests matter more than speed of delivery.
Mechanical rules (formatting, import order, docstring and annotation
presence) are enforced by `ruff` (see `pyproject.toml`); run `tools/lint`
before considering a change done. `tests/test_lint.py` fails otherwise.

## Layout

- `gem5/`: code that must be integrated *inside the simulator* (vendored gem5
  24.0 + Ramulator2). Changes to it are listed in `gem5/PATCHES.md`; add to
  that list whenever you touch it. Programs that run *on* the simulator do
  not go here.
- `src/leakyhammer/`: importable Python and the non-importable C++ programs
  that run on the simulator. **It has no `main` functions** (no `__main__`
  blocks, no argparse) **and produces no artifacts**: no results, no figures.
  It holds utilities for driving gem5.
  - `defenses.py`: one `Defense` entry per defense (config, window, noise
    rates, POC parameters) and `Variant` (a defense with plugin overrides).
  - `sim.py`: builds and runs gem5 commands (`Simulation`).
  - `metrics.py`: log parsing, BER, capacity.
  - `results.py`: the result store (`results/<experiment>/<batch>/<trial>/`).
  - `config.py`: loading and validating sweep YAML.
  - `attacks/`: guest-side C++ (`<defense>/{sender,receiver,poc_sender,
    poc_receiver}.cc`, `common/`, `noise/`, `latency/`) and `build.py`.
- `src/leakyhammer/experiments/<name>/`: programs that *produce* results (and
  the figures of those results). Every experiment has:
  - `README.md`: at a minimum, how to run it and what data it provides;
  - `main.py`: generates a *single* artifact (and holds the experiment's
    config types, since `main`, `run` and `plot` all read it);
  - `configs/<config>.yaml`: describes a sweep of artifacts to collect;
  - `run.py`: generates the sweep; `--config` is a required argument;
  - `plot.py`: draws the figures for a sweep (all of the experiment's plots can
    live in this one file); `--config` is a required argument.
- `tests/`: unit, integration and experiment tiers (see "Tests").
- `tools/`: command-line entry points for development: `build`,
  `compile-attacks`, `lint`, `gem5-diff`, and `replicate-report` (reruns the
  report's measurements; see `docs/replication.md`). Command lines live here or in an
  experiment, never in the core library.
- `docs/`: how-tos (`adding-a-defense.md`, `experiments.md`), how the
  report's numbers are reproduced (`replication.md`), and the DREAM-C design
  and results (`dream-c.md`).
- `src/leakyhammer/attacks/legacy/`: code kept verbatim from history only so
  the report can be reproduced. It is not a model for new work.
- Generated and gitignored: `build/`, `results/`, `.venv/`, `gem5/build/`.

## Python

Python 3.8 (it matches the container's system Python, which gem5 embeds), so:
`Optional[X]`/`Dict[str, Any]` from `typing`, not `X | None` or `dict[...]`.
Every parameter and return value is annotated, including `self`, annotated
with the class name as a string: `def run(self: "Simulation") -> Path:`.
Every module, class, and public function has a Google-style docstring (a
one-line summary is fine). Module docstrings are one line at the very top;
document a module-level constant with a string *after* its assignment.

Comments are rare and explain *why*, as full sentences with a capital letter
and trailing period, on the line(s) before the code they explain.

- Importing a module never does work: no argparse, no file or process side
  effects at import time. Put it in a function and call it from `main()`.
- Prefer small, direct functions over frameworks. Don't add configurability
  that isn't needed yet; delete dead code instead of commenting it out.
- `subprocess.run(cmd, check=True)` for things that must succeed; build
  commands as argument lists, never by string formatting into a shell line.
- Raise specific built-ins with an f-string naming the offending value
  (`raise ValueError(f"Unknown defense '{name}'")`).
- matplotlib's `pyplot` is not thread-safe: run simulations in threads if you
  like, but draw figures from one thread.
- Don't refer to a paper's figure or table numbers in source files (code,
  comments, docstrings, tests). Say what the figure shows instead.
- One plot file may draw many figures; don't split a file per figure.
  Combine near-duplicates behind a small per-case style table.
- Core library files are not executable: no `__main__` blocks, no scripts.

## Experiments and results

An experiment is a package under `src/leakyhammer/experiments/`. `main.py`
runs one trial and stores one record; `run.py` expands a YAML config into
trials; `plot.py` reads the *same* config to know which records to look for.
See `docs/experiments.md`.

- Record everything a result depends on in its `result.json`: the parameters,
  the git revision, a hash of the Ramulator config actually used (including
  per-trial overrides), and hashes of the guest programs
  (`results.provenance`).
- Never drop a failed trial. Store it with `status: "failed"` and the error,
  and let aggregation refuse to average over it (`metrics.summarize`).
- Pass settings that affect results explicitly; don't rely on tool defaults.
  Sweep a plugin parameter with config `overrides`, never by editing a
  tracked YAML.
- Simulation results are deterministic, but they depend on the guest's memory
  layout, so three seemingly irrelevant things change them (each was found
  the hard way; BER shifts of a few percent, POC outcomes flip a bit):
  1. the **compiler** of the attack programs: plain `g++` (9.4), never
     `$CXX` (the container exports g++-10); see `attacks/build.py`;
  2. the **source paths embedded in the binaries** (`assert` strings):
     `build.py` maps them to the original artifact's names;
  3. the **strings on the guest's stack**: the program path (`argv[0]`) and
     the noise generator's period written as a float (`24000000.0`);
     `sim.py` passes `./<name>` from a fixed working directory so the result
     does not depend on where the repo is cloned.
  Never "clean up" any of these without re-measuring against
  `tests/integration/test_gem5.py` and the reference values in
  `docs/experiments.md`.
- Don't change behavior that past results depend on without saying so (the
  `Defense` windows, the 32 GB memory size, the receiver timeouts).

## Tests

This project is test-driven; a change isn't done until it is tested.

- A new feature gets tests that exercise its real code path; assert behavior,
  not constants. A bug fix gets a `@pytest.mark.regression` test that fails
  without the fix, with the old failure explained in the docstring.
- Tiers, by marker (`conftest.py` requires every test to have one):
  - `unit`: no gem5, no compiler. Monkeypatch `Simulation.run` rather than
    starting gem5, and build the logs and tables you need with the fixtures in
    `tests/conftest.py` (`transmission_log`, `poc_log`, `noise_csv`,
    `latency_log`), which print the real formats. Do not commit data files:
    `tests/data/` is gitignored.
  - `integration` + `slow`: the core library against a real simulator
    (`tests/integration/`).
  - `experiment` + `slow`: an experiment end to end (`tests/experiments/`).
  Tiers that need gem5 request the `require_simulator` fixture and skip
  cleanly when it is not built, so a bare `uv run pytest` always works.
- Test functions are `test_*`, return `-> None`, and have a one-line
  docstring saying what they verify.
- Run `uv run pytest -m "not slow"` always; `uv run pytest -m "integration or
  experiment"` after touching anything that reaches gem5 (about two minutes).
  Report which tiers you did not run.

## Resources

Each gem5 run peaks near 3 GB of RAM. `run.py` defaults to 4 parallel runs;
raise `-j` only to what the machine's free memory allows. Never run
host-wide destructive commands; clean up only what you created.
