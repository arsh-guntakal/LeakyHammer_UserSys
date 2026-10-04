# Adding a defense

A defense plugs into every experiment (noise sweep, POC) through one entry in
`src/leakyhammer/defenses.py`. The pieces, using DREAM-C as the template:

1. **Ramulator2 plugin.** Add `<name>.cpp` under
   `gem5/ext/ramulator2/ramulator2/src/dram_controller/impl/plugin/` and list it
   in that directory's `src/dram_controller/CMakeLists.txt`. Plugins are built
   into `libramulator.so` by Ramulator's CMake, so they live beside it. Rebuild
   with `tools/build --ramulator` (gem5 picks up the new library at run
   time) and add the file to `gem5/PATCHES.md`.

2. **Ramulator config.** Copy `gem5/configs/rhsc/ramulator/dream.yaml` to
   `<name>.yaml` and point its `ControllerPlugin` at your plugin. Any
   parameter in that plugin entry can be swept later without editing the file
   (see `overrides` in `experiments.md`).

3. **Attack programs.** Create `src/leakyhammer/attacks/<name>/` with
   `sender.cc`, `receiver.cc`, `poc_sender.cc`, `poc_receiver.cc` (copy the
   DREAM or RFM ones). They share `common/rowhammer-side.{cc,hh}` and
   `rowhammer-addr.hh`. The build picks them up automatically
   (`tools/compile-attacks`).
   - The programs must print the lines the parser reads:
     `[<NAME>-SEND] Binary: <bits>`, `[<NAME>-RECV] Binary: <bits>`,
     `[<NAME>-RECV] Received in <ns> ns`. Receivers should also print
     `Resyncs:` and `MinSleepAssert:` (a negative slack or any resync means the
     run is suspect). POC receivers print either one `Binary:` line or one
     `Received: <bit> (<n> ...)` line per window.
   - If the attack depends on plugin state (DREAM's XOR masks), the userspace
     copy must match the plugin bit for bit; the plugin prints its table at
     start-up so you can check.
   - The physical-address layout in `rowhammer-addr.hh` must match Ramulator's
     `RoBaRaCoCh_with_rit` mapper.

4. **Register it.** Add a `Defense(...)` to `DEFENSES`: config file, window
   (`txn_period_ns`), noise rates, POC options, and `plugin_impl` if it has
   tunable parameters.

5. **POC figure.** Add the defense to `plot_poc` in
   `src/leakyhammer/experiments/poc/plot.py` (reuse `_plot_counts` if its
   receiver prints one count per window, as RFM and RRS do), and to the
   experiments' configs (`configs/*.yaml`) that should include it.

6. **Tests.** `tests/test_defenses.py` already checks every registered
   defense has a config and all four sources. If your logs have a new shape,
   extend the builders in `tests/conftest.py` (`transmission_log`, `poc_log`)
   and add a parse test; do not commit log files.

7. **Check it works.**

   ```bash
   tools/compile-attacks
   python -m leakyhammer.experiments.poc.main --defense <name>
   python -m leakyhammer.experiments.noise_sweep.run --config quick   # add <name> to the config first
   uv run pytest -m "not slow"
   ```

Run a baseline before trusting any numbers: confirm the receiver reports
`Resyncs: 0`, a positive `MinSleepAssert`, and that a defense known to leak
(RFM) still decodes `MICRO` with your build.
