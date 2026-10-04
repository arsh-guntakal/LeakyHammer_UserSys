# LeakyHammer + DREAM-C + RRS (UT Austin extension)

This repository extends the MICRO 2025 LeakyHammer artifact
([paper](https://arxiv.org/abs/2503.17891), original README: [ARTIFACT_README.md](ARTIFACT_README.md))
with two newer RowHammer defenses, evaluated with the same covert-channel attack:

| Defense | Ramulator plugin | Attack binaries | Config |
|---|---|---|---|
| PRAC, RFM | original artifact | `prac_*`, `rfm_*` | `prac.yaml`, `rfm.yaml` |
| **DREAM-C** (new) | `dram_controller/impl/plugin/dream.cpp` | `dream_*`, `dream_poc_*` | `dream.yaml` |
| **RRS** (plugin from the artifact; harness new) | `dram_controller/impl/plugin/rrs.cpp` | `rrs_*`, `rrs_poc_*` | `rrs.yaml` |

Results are written up in `base-project-report.pdf`. Deeper notes live in
`AGENTS.md` (project history, DREAM design) and `RECEIVER_DRIFT_FIX.md`
(receiver phase-drift bug). Treat `AGENTS.md` numbers as historical; this README is
what was last re-verified (see "What was verified").

## 1. Environment

Everything runs on **Ubuntu 20.04, Python 3.8, g++-10** inside the project container.
Build the image from the `Dockerfile` (it installs apt packages, `uv`, and runs
`uv sync --frozen`):

```bash
docker build -t leakyhammer .
# Mount the repo so edits/results persist. The mount hides the image's .venv,
# so run `uv sync --frozen` once inside to recreate it on the host.
docker run --rm -it -v "$PWD":/app/LeakyHammer_UserSys leakyhammer bash
cd /app/LeakyHammer_UserSys && uv sync --frozen
```

All commands below run **inside the container**, from `gem5/` unless stated.
Paths are derived from the script locations, so no path editing is needed.

> Do not run gem5 or `scons` with the uv venv's Python on `PATH`: gem5 embeds the
> *system* Python, and mixing the two aborts with `No module named '_contextvars'`.
> `rebuild.sh` handles this for you. The Python analysis scripts (pandas etc.) do want
> the venv: use `../.venv/bin/python3` or `source ../.venv/bin/activate` for those only.

## 2. Build (once, and after C++ changes)

```bash
cd gem5
JOBS=64 ./rebuild.sh --all      # Ramulator (libramulator.so) + gem5.opt + m5 util
./compile_attack_scripts.sh     # all sender/receiver/POC binaries -> attack-binaries/
```

`JOBS` defaults to 8 (Ramulator) / 2 (gem5); raise it on big machines. The gem5 link takes
tens of minutes. What to rebuild after an edit:

| You edited | Run |
|---|---|
| `gem5/attack-scripts/*` | `./compile_attack_scripts.sh` |
| `gem5/ext/ramulator2/**` (plugins, `DDR5-VRR.cpp`) | `./rebuild.sh --ramulator` (gem5 picks up the new `.so` via RPATH) |
| `gem5/configs/**` (YAML or Python) | nothing |

`rebuild.sh` stops with a non-zero exit on any build failure (it used to print
"success" regardless).

## 3. Reproduce the results

### 3a. Proof of concept (~1 min each)

```bash
poc-scripts/run_poc.sh rfm      # expect: 'MICRO' decoded, 0/40 errors
poc-scripts/run_poc.sh dream    # expect: 'UTECE' -> 'd??&L', 18/40 errors (report Fig. 7)
poc-scripts/run_poc.sh rrs      # expect: 'MICRO' -> mostly garbage, ~16/40 errors (see caveat)
```

Logs go to `gem5/results/poc/`. The simulation is deterministic: DREAM reproduces the
report's 18/40 and `d??&L` exactly.

### 3b. Full matrix: BER and capacity vs. noise (~70 min at 34 parallel)

```bash
python3 result-scripts/setup_test.py          # writes run_scripts/*.sh and run.sh (68 runs)
cat run.sh | sed 's/^sh //' | xargs -I{} -P32 sh {}
../.venv/bin/python3 result-scripts/parse_and_print.py   # CSVs, summary, figures/*.pdf
```

One run takes about 7 minutes and ~3 GB RAM. The old guidance of `-P4` was for a
desktop; size `-P` to roughly (free RAM / 3 GB) and your core count. Host parallelism does not
change simulated results. (`setup_test.py -c` generates docker-wrapped scripts; that path
is the pre-uv layout and is **not** verified.)

Outputs: `results/<defense>/{baseline,noise}/*.txt` (raw logs), `results/*ber*.csv`,
`figures/figure4.pdf` (PRAC), `figure7.pdf` (RFM), `figure7_dream.pdf`, `figure7_rrs.pdf`.

Sanity checks in each receiver log: `Resyncs: 0` and a positive `MinSleepAssert` mean the
receiver stayed in phase. (The original PRAC receiver shows negative `MinSleepAssert` in a
few runs; that code is unmodified from the artifact.)

### 3c. What I got vs. the report (Table 1)

Capacity = raw rate x (1 - H(mean BER)), over 4 data patterns; "noise" = mean over the
noise rates in `result-scripts/run_config.py`.

| Defense | Raw Kbps (report / re-run) | Baseline BER | Baseline cap | Mean noise cap |
|---|---|---|---|---|
| PRAC  | 39.02 / 39.02 | 0.036 / 0.0356 | 30.36 / 30.36 | 13.47 / 13.47 |
| RFM   | 48.77 / 48.77 | **0.000** / 0.187 | **48.77** / 14.88 | 46.71 / 46.63 |
| DREAM-C (T_TH=40) | 48.77 / 48.77 | 0.478 / 0.478 | 0.067 / 0.069 | 0.130 / 0.131 |
| RRS | 46.12 / 46.0-46.2 | 0.42 / 0.431 | 0.85 / 0.635 | 0.91 / 0.738 |

- **PRAC and DREAM-C match the report** (PRAC exactly).
- **RFM noise matches; RFM baseline does not.** The report lists baseline BER 0.000; the
  code gives 0.187 (0% on `0x00`, ~13% on `0x55`/`0xAA`, ~49% on `0xFF`). `AGENTS.md`
  independently recorded 0.197, so the report's 0.000 looks wrong or from a different build.
- **RRS is the right order of magnitude but not reproduced exactly** (see below).
- The DREAM `T_TH` sweep (62/125/250/500) is documented in `AGENTS.md` section 6.1 but was **not**
  re-run for this README. To do it, edit `threshold` in `configs/rhsc/ramulator/dream.yaml`,
  clear `results/dream/`, rerun the DREAM runs only.

### 3d. RRS caveats (unresolved)

- The RRS plugin is the artifact's own `rrs.cpp`. This repo adds the sender, receiver,
  config and harness wiring. (An earlier `srs.cpp` was a renamed copy and has been removed.)
- Report: N_TH = 40 and a receiver band "calibrated" to a 400-500 ns spike. Repo:
  `rrs.yaml` has `rss_threshold: 50` and `rowhammer-side.hh` uses
  `RRS_SWAP_CAP_NS = 3000` (marked TODO), so the receiver likely isn't looking at the swap
  signature at all. Setting N_TH = 40 gives 19/40 POC errors, not the report's 14/40.
- The RRS receiver has no drift fix or resync (unlike RFM/DREAM).
- Treat RRS numbers as "weak/no channel", not as a replication of the report's exact values.

## 4. Repository map

```
gem5/attack-scripts/    sender/receiver C++ (rowhammer-side.* is the shared library)
gem5/compile-scripts/   per-target recompile scripts
gem5/configs/rhsc/ramulator/   YAML per defense (prac, rfm, dream, rrs)
gem5/ext/ramulator2/    vendored Ramulator2 (plugins in src/dram_controller/impl/plugin/)
gem5/result-scripts/    run_config.py (experiment definition), setup_test.py, parse_and_print.py, decode_poc.py
gem5/plot-scripts/      figure plotters
gem5/poc-scripts/       run_poc.sh
```

Generated, git-ignored: `gem5/{results,run_scripts,attack-binaries,build}`, `gem5/run*.sh` lists.

## 5. Contributing

**Workflow**
- Branch from `organize` (or `master` once `organize` is merged); one topic per branch,
  descriptive names (`feat/add-moat`, `fix/prac-receiver-noise`). Don't leave work stranded on
  a side branch: the RRS work sat unmerged on `row-swap` and diverged from the DREAM fixes.
- Small, reviewable commits with messages saying *why*. Never commit `results/`, binaries,
  `build/`, `.venv`, or logs. Don't commit absolute host paths (generated `run*.sh` contained them).
- Before opening a PR: rebuild from clean, run the three POCs (3a), and for any change that
  could affect timing, rerun the affected rows of the matrix and update the table in 3c.

**Adding a defense** (use DREAM/RRS as templates)
1. Plugin `.cpp` under `plugin/` and register it in `src/dram_controller/CMakeLists.txt`.
2. `configs/rhsc/ramulator/<name>.yaml`.
3. `rowhammer-<name>-{sender,receiver}.cc`, `<name>-poc-*.cc`, and shared helpers in
   `rowhammer-side.{cc,hh}`; `compile-scripts/recompile_<name>.sh` and
   `recompile-<name>-poc.sh`; add both to `compile_attack_scripts.sh`.
4. A preset in `get_preset_variables()` in `run_config.py`; add the name to the preset lists
   in `setup_test.py` and `parse_and_print.py` (baseline **and** noise).
5. Log tags `[<NAME>-SEND]` / `[<NAME>-RECV]` (the parser regex accepts `[A-Z]+-` prefixes).
6. Add a `run_poc.sh` case.

**Gotchas that have already cost time**
- If the attack depends on plugin state (DREAM's XOR masks), the userspace copy must match
  the plugin bit-for-bit; keep `seed`, entry counts and bank counts in sync. The plugin
  prints its mask table at startup.
- Physical-address layout in `rowhammer-addr.hh` must match Ramulator's
  `RoBaRaCoCh_with_rit` (bank-group below bank; 64-bit `Addr_t`). `--mem-size=32GB` is needed
  for DREAM's two-bank collision addresses.
- Edits under `ext/ramulator2/` need `./rebuild.sh --ramulator`; stale `.so` symptom is
  results bit-identical to a previous run.
- Per-run `--m5-outdir` requires the `FileSystemConfig.py` fix in this repo (redirect
  paths used the wrong directory and gem5 segfaulted).
- `pd.read_csv` on BER CSVs needs `dtype={'sent': str, 'received': str}`.

## 6. What was verified (and not)

Verified by a full build and run in an Ubuntu 20.04 container (no docker daemon available
in that session): Ramulator + gem5 build, all attack binaries, the three POCs, the entire
68-run matrix, parsing and figure generation. **Not** verified: building the image from the
`Dockerfile` and the `docker run` mount flow in section 1, `setup_test.py -c`, the Slurm scripts,
the DREAM T_TH sweep, and the side-channel (website fingerprinting) experiments.
