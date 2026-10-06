# noise_sweep

How well can a sender and receiver communicate through a defense, with and
without background memory traffic?

## What it measures

For each defense (and plugin-parameter variant), a sender transmits a message
of one repeated data byte through the defense's latency side effects while a
receiver decodes it. Each configuration is run for several data patterns, once
without noise and once per background-noise rate. From the decoded bits it
reports:

- **bit error rate (BER)**: 0 is a perfect channel, 0.5 is a closed one;
- **raw rate** (Kbps) and **channel capacity** `raw * (1 - H(BER))` (Kbps).

One trial is one gem5 simulation (about 7 minutes, 3 GB of RAM).

## Run it

```bash
# Collect a sweep (resumes where it left off; -j sets parallel simulations).
python -m leakyhammer.experiments.noise_sweep.run --config default -j 32

# Tables, per-defense CSVs, and capacity-versus-noise figures.
python -m leakyhammer.experiments.noise_sweep.plot --config default

# Just one trial, e.g. RFM with noise:
python -m leakyhammer.experiments.noise_sweep.main --defense rfm \
    --pattern 0x55 --noise-rate 263
```

Both `run` and `plot` require `--config` (a name from `configs/` or a YAML
path) and read the same file, so the figures always describe exactly the
trials that were collected. `run --dry-run` prints one shell command per trial
for your own scheduler.

## Configs

| Config | Trials | What it sweeps |
|---|---|---|
| `default` | 68 | PRAC, RFM, DREAM-C, RRS; 4 data patterns; baseline + noise |
| `quick` | 17 | the same defenses, one data pattern |
| `dream_threshold` | 80 | DREAM-C's threshold `T_TH` in 40/62/125/250/500 |
| `rrs_threshold` | 32 | RRS's swap threshold in 40/50 |
| `report` | 68 | The measurements behind the report's Table 1 (run with `tools/replicate-report`) |

Keys: `variants` (a `defense`, optional plugin `overrides`, optional
`noise_rates`, and optional `baseline`/`noise` switches that override the
sweep-wide ones for that variant), `patterns`, `msg_bytes`, `baseline`, `noise`.

## Choosing noise rates

The figure reports capacity at a reference intensity (88% for PRAC, 50% for the
others), where intensity is each rate's position between the smallest and
largest rate in the sweep. The sweep must therefore contain a rate that lands
within 1% of that point, or the figure fails with an `IndexError`. The defaults
(PRAC 275/475/1075/1975, others 200/263/325) were chosen so 475 and 263 hit it;
if you change `noise_rates`, check this first.

## Output

`results/noise_sweep/<batch>/<trial>/` holds the raw log and `result.json`
(parameters, decoded bits, BER, provenance). `plot` writes
`<batch>/analysis/ber_<variant>.csv`, `noise_ber_<variant>.csv` and
`noise_<variant>.pdf`. See `docs/experiments.md` for the record format.
