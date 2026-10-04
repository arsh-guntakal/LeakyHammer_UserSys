# Experiments

An experiment is a package under `src/leakyhammer/experiments/<name>/`:

| File | Role |
|---|---|
| `README.md` | How to run it and what data it provides. |
| `main.py` | Run **one** trial and store one record (also holds the config types). |
| `configs/*.yaml` | Named configs; one file describes one sweep of trials. |
| `run.py` | Expand a config into trials and run them; `--config` is required. |
| `plot.py` | Tables, CSVs and figures from stored records; `--config` is required. |

## Available experiments

| Experiment | What it measures | Typical command |
|---|---|---|
| `noise_sweep` | BER and capacity per defense, with and without background noise. | `python -m leakyhammer.experiments.noise_sweep.run --config default -j 32` |
| `poc` | A short text message through each defense. | `python -m leakyhammer.experiments.poc.run --config default` |
| `latency_profile` | Single-process access latency under PRAC, showing the back-off spikes. | `python -m leakyhammer.experiments.latency_profile.run --config default` |

Each experiment's own `README.md` says how to run it and what data it provides.

Run commands from the repository root with the uv environment
(`uv run python -m ...`, or the container's `.venv`).

## Noise-sweep configs

```yaml
patterns: ["0x00", "0x55", "0xAA", "0xFF"]   # data bytes to send
msg_bytes: 100                               # message length (8 bits each)
baseline: true                               # include the no-noise runs
noise: true                                  # include the noise-rate runs
variants:
  - defense: dream
    overrides: {threshold: 62}               # plugin parameter overrides
    noise_rates: [200, 263, 325]             # optional; default per defense
```

- `variants` are what is measured. `overrides` edit the defense's plugin
  parameters for that variant only (a per-trial copy of the Ramulator config is
  written and hashed into the record); unknown parameters are rejected.
- Provided configs: `default` (the full 68-run matrix), `quick` (17 runs),
  `dream_threshold` (T_TH sweep, 80 runs), `rrs_threshold` (32 runs).
- `run.py` options: `--config NAME|PATH`, `-j N` (default 4), `--force`,
  `--batch NAME`, and `--dry-run`, which prints one shell command per trial.
  Feed that to `xargs -P` or a scheduler such as Slurm instead of using `-j`.
- The runner skips trials that already have a successful record, so an
  interrupted sweep resumes by re-running the same command.

## Where results go

```
results/<experiment>/<batch>/<trial>/
    sim.log          raw simulator output
    m5out/           gem5's own output (stats, config, fake /proc)
    ramulator.yaml   only when overrides were used
    result.json      the record
results/noise_sweep/<batch>/analysis/   CSVs and figures from plot.py
```

`LEAKYHAMMER_RESULTS=/path` moves the root. Directories are safe to browse,
edit and delete by hand; a trial without `result.json` is simply re-run.

`result.json` holds the parameters, `status` (`ok` or `failed`), the sent and
received bits, `errors`, `ber`, the receiver's `resyncs` and `min_sleep_assert`,
and `provenance`: the git revision, a hash of the Ramulator config actually used,
and a hash of every guest program. Failed trials keep every key and an `error`;
`plot.py` reports them and refuses to average over them.

## Reproducibility

Results are deterministic, and they are sensitive to the guest's memory
layout. Three things you would not expect to matter do:

| What | Where it is fixed |
|---|---|
| The attack programs' compiler: plain `g++` 9.4, **not** the container's `CXX=g++-10` | `attacks/build.py` (override: `LEAKYHAMMER_CXX`) |
| The source paths the compiler embeds in each program | `attacks/build.py` maps them to the original artifact's names |
| The strings on the simulated stack: the program path and the noise period | `sim.py` (`./<name>` from the binaries directory; the period as `24000000.0`) |

With these fixed, a program built here is byte-identical to the original
artifact's in every loaded section (`.text`, `.rodata`, `.data`, `.eh_frame`).

**Comparing with measurements made before the reorganization.** Those ran with
guest programs at `/app/LeakyHammer_UserSys/gem5/attack-binaries/<name>`. The
default `./<name>` is shorter, which shifts some results slightly (PRAC's
baseline timing by tens of ns, RFM's `0xFF` baseline by a few dozen bit
errors). To reproduce the old numbers bit for bit, pin a guest directory whose
path has the *same length* and contains the binaries:

```bash
cp -r build/attack-binaries /app/LeakyHammer_UserSys/gem5/attack-binaries  # or any 45-character path
LEAKYHAMMER_GUEST_BIN_DIR=/app/LeakyHammer_UserSys/gem5/attack-binaries \
    python -m leakyhammer.experiments.noise_sweep.run --config default
```

`LEAKYHAMMER_GUEST_BIN_DIR` pins an absolute directory for the guest programs
(gem5 then runs from the current directory instead of the binaries
directory). Whatever you choose, record it with your results.

## Plotting

```bash
python -m leakyhammer.experiments.noise_sweep.plot --config default
```

prints a table (raw Kbps, mean BER, capacity per defense and kind) and writes
`ber_<variant>.csv`, `noise_ber_<variant>.csv` and `noise_<variant>.pdf` into
the batch's `analysis/`. Capacity is `raw * (1 - H(mean BER))`, as in the
LeakyHammer paper.

## Adding an experiment

1. Create the package with `README.md`, `main.py` (one trial; store a record
   with `results.save_record`, include `results.provenance`; define the config
   types here), `configs/`, `run.py` and `plot.py` (both take a required
   `--config`). Put the experiment's plotting code in `plot.py`; the core
   library draws nothing.
2. Call the simulator through `leakyhammer.sim` rather than building gem5
   commands by hand.
3. Add tests under `tests/experiments/` that fake `Simulation.run` with a log
   from the builders in `tests/conftest.py`, so they run in milliseconds, plus
   one `experiment`-marked end-to-end test.
4. Don't draw figures from worker threads (see `CLAUDE.md`).
