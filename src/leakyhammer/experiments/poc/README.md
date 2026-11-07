# poc

Can a short text message cross the defense's covert channel?

## What it measures

The sender transmits a five-character message (40 bits) and the receiver
decodes it, with no background noise. This is the most favorable case for the
attacker, so a failure here is a hint, not a verdict: the attack may be
broken (see `docs/attack-validity.md`). It reports the sent and
decoded text and the number of bit errors; the figure shades each window by the
bit that was sent and plots what the receiver measured.

PRAC and RFM send `MICRO`, DREAM-C sends `UTECE`, RRS sends `MICRO`. A vulnerable
defense (RFM) decodes it exactly. One run takes about a minute.

## Run it

```bash
python -m leakyhammer.experiments.poc.run --config default     # runs + decodes
python -m leakyhammer.experiments.poc.plot --config default    # draws figures

# One defense, optionally with a plugin parameter changed:
python -m leakyhammer.experiments.poc.main --defense dream --set threshold=62
```

`run` and `plot` require `--config`.

## Configs

| Config | What it runs |
|---|---|
| `default` | PRAC, RFM, DREAM-C, RRS |
| `dream_threshold` | DREAM-C at each threshold of the sweep |

## Output

`results/poc/<batch>/<defense>/` holds `sim.log`, `result.json` (sent and
decoded text, errors, BER, receiver resyncs, provenance) and, after `plot`,
`figure.pdf`. Expected results are in the repository README.
