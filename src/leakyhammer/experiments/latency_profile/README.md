# latency_profile

What does a memory access look like when PRAC fires?

## What it measures

A single process times back-to-back memory requests to a few rows. Most are
row-buffer conflicts; periodic refreshes and PRAC back-offs show up as much
slower accesses. The figure marks the three latency bands, which is the
observation the covert channel is built on: the defense's action is visible
from user space as a latency spike.

Only the `prac` defense is meaningful (the bands are PRAC's). One run takes
under a minute.

## Run it

```bash
python -m leakyhammer.experiments.latency_profile.run --config default
python -m leakyhammer.experiments.latency_profile.plot --config default

# Or just one profile:
python -m leakyhammer.experiments.latency_profile.main
```

`run` and `plot` require `--config`.

## Output

`results/latency_profile/<batch>/prac/` holds `sim.log` (the latency dump),
`result.json` (status and provenance) and, after `plot`, `figure.pdf`.
