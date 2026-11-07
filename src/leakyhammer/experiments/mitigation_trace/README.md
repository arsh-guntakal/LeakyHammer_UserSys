# mitigation_trace

Does DREAM-C's plugin mitigate correctly: deterministically, and in
proportion to how much it is actually hammered?

## What it measures

This is a narrower question than the covert channel. BER and capacity (see
`noise_sweep`, `poc`) ask whether an *attacker's receiver* can decode the
defense's actions; this experiment asks whether the *defense itself* does
what it is specified to do, with no receiver running at all. The DREAM-C
plugin prints a line every time its DCT counter crosses the threshold and it
issues a DRFMab (`dream.cpp`'s "T_TH hit" log, enabled by the `debug` plugin
parameter). This experiment runs the DREAM-C sender alone under each of four
data patterns and counts those lines.

Every send hammers through a fixed 8-window calibration preamble regardless
of the message (`DREAM_ACTIVE_WINDOWS` in `dream_attack.hh`), so even `0x00`
(a message with no set bits) hammers those 8 windows. `0x55`, `0xAA` and
`0xFF` add an increasing share of the message's windows on top. Mitigations
should scale with the total number of windows actually hammered: a plugin
whose counter and threshold logic work as designed does not mitigate some
fixed amount regardless of input, and does not mitigate zero times despite
genuine hammering. This is the precondition for everything `noise_sweep`,
`poc` and `latency_histogram` say about leaking: a defense that did not
mitigate correctly could not leak through its mitigation.

## Run it

```bash
python -m leakyhammer.experiments.mitigation_trace.run --config default
python -m leakyhammer.experiments.mitigation_trace.plot --config default

# Or one pattern:
python -m leakyhammer.experiments.mitigation_trace.main --pattern 0xFF
```

`run` and `plot` require `--config`. One run takes under a minute.

## Output

`results/mitigation_trace/<batch>/threshold<T_TH>_p<pattern>/` holds `sim.log`
and `result.json` with the mitigation and hammering-window counts. `plot`
prints a table and writes `figure.pdf`.
