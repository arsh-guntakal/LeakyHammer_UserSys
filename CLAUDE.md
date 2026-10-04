# Style guide

This file tells contributors (human or Claude) how to write code that looks
like it belongs here. This is a research project: results must be
reproducible, so correctness and tests matter more than speed of delivery.
Mechanical rules (formatting, import order, docstring and annotation
presence) are enforced by `ruff` (see `pyproject.toml`); run `tools/lint`
before considering a change done. `tests/test_lint.py` fails otherwise.

## Layout

- `src/leakyhammer/`: the importable core.
  - `defenses.py`: one `Defense` entry per defense (config, window, noise
    rates, POC parameters). The single place experiments learn about defenses.
  - `sim.py`: builds and runs gem5 commands (`Simulation`).
  - `metrics.py`: log parsing, BER, capacity.
  - `results.py`: the result store (`results/<experiment>/<batch>/<trial>/`).
  - `attacks/`: guest-side C++ (`<defense>/{sender,receiver,poc_sender,
    poc_receiver}.cc`, `common/`, `noise/`, `latency/`) and `build.py`.
  - `plotting/`: figure code, one function per figure.
  - `experiments/<name>/`: `main.py` (one trial), `run.py` (a sweep driven by
    a YAML config in `configs/`), `plot.py` (tables/figures from stored
    results).
- `tests/` mirrors the package; `tests/experiments/` tests the experiments;
  `tests/data/` holds small real logs used as fixtures.
- `gem5/`: the vendored simulator (gem5 24.0 + Ramulator2). Changes to it are
  listed in `gem5/PATCHES.md`; add to that list whenever you touch it.
- `tools/`: `build`, `lint`, `gem5-diff`.
- `docs/`: how-tos (`adding-a-defense.md`, `experiments.md`) and the
  historical project notes (`dream-history.md`).
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
  `tests/test_simulation_integration.py` and the golden values in
  `docs/experiments.md`.
- Don't change behavior that past results depend on without saying so (the
  `Defense` windows, the 32 GB memory size, the receiver timeouts).

## Tests

This project is test-driven; a change isn't done until it is tested.

- A new feature gets tests that exercise its real code path; assert behavior,
  not constants. A bug fix gets a `@pytest.mark.regression` test that fails
  without the fix, with the old failure explained in the docstring.
- Tiers by marker: `unit` (no gem5, no compiler; use the small logs in
  `tests/data/` and monkeypatch `Simulation.run` rather than starting gem5),
  `integration` + `slow` (needs the built simulator; skip cleanly otherwise).
  Every test has a marker (`conftest.py` enforces it).
- Test functions are `test_*`, return `-> None`, and have a one-line
  docstring saying what they verify.
- Run `uv run pytest -m "not slow"` always; `uv run pytest -m integration`
  after touching anything that reaches gem5 (a DREAM POC takes ~1 minute).
  Report which tiers you did not run.

## Resources

Each gem5 run peaks near 3 GB of RAM. `run.py` defaults to 4 parallel runs;
raise `-j` only to what the machine's free memory allows. Never run
host-wide destructive commands; clean up only what you created.
