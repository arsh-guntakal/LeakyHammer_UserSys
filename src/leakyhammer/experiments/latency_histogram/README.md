# latency_histogram

Can a process that is not the sender see the sender's activity at all?

## What it measures

A diagnostic receiver decodes nothing. It probes memory continuously and counts,
for every window, how many probes fell in each latency bin. The sender
transmits a repeating byte. If a defense's action is visible to the receiver,
windows where the sender sent a 1 have more slow probes than windows where it
sent a 0.

This is how to tell a channel that is *closed* from an attack that is
*broken*: a decoder that reports BER 0.5 cannot say which. The histogram does.

- `rfm` is the positive control. Its stall is visible, so if the tool shows no
  difference for it, the tool (or the probe placement) is wrong, and no other
  row of the table means anything.
- `rrs` and `dream` are the cases in question. See `docs/attack-validity.md`
  for what the numbers have shown so far.

## Run it

```bash
python -m leakyhammer.experiments.latency_histogram.run --config default
python -m leakyhammer.experiments.latency_histogram.plot --config default

# Or one measurement:
python -m leakyhammer.experiments.latency_histogram.main --defense rfm \
    --probe-rows 1 --first-row 1 --bank-group 7 --bank 3
```

`run` and `plot` require `--config`. A variant sets where the receiver probes
(`probe_rows`, `first_row`, `bank_group`, `bank`) and `sync_ns`, when the sender
starts: 220000 for most senders, 1500000 for DREAM-C (its receiver maps many
rows first). A receiver that misses its start is recorded as failed instead of
reported as "no difference".

## Output

`results/latency_histogram/<batch>/<variant>/` holds `sim.log` and `result.json`
with the mean probes per bin for windows of 1 and of 0. `plot` prints the extra
slow probes (>= 250 ns) per window of a 1 and writes `figure.pdf`.
