# TPRAC

How the TPRAC defense is modeled, how it is attacked, and what we measured. TPRAC
is from *When Mitigations Backfire: Timing Channel Attacks and Defense for
PRAC-Based RowHammer Mitigations* (Woo, Qu, Saileshwar and Nair, ISCA 2025),
which was designed against exactly the channel LeakyHammer measures.

## The defense

PRAC leaks because the attacker decides when its mitigation happens: hammering
a row to the back-off threshold raises an Alert Back-Off (ABO), and the
resulting ~1.4 us stall is visible to every other core. TPRAC keeps PRAC's
per-row counters and adds **timing-based RFMs**: one RFMab per rank every
`tb_rfm_window_ns`, whatever the activations are. Each RFM mitigates the most
activated row of every bank, so with a short enough window no counter reaches the
ABO threshold, and the only mitigation latency left is periodic and carries no
data.

## The model

- `gem5/ext/ramulator2/ramulator2/src/dram_controller/impl/plugin/tprac.cpp`
  schedules the RFMs. It is ported from the authors' `TimingBasedRFM` plugin
  ([STAR-Laboratory/PRAC_TC_ISCA25](https://github.com/STAR-Laboratory/PRAC_TC_ISCA25)),
  without its optional targeted-refresh path, which their TPRAC configurations
  leave off. The RFMs go through `priority_send`, like refreshes.
- `gem5/configs/rhsc/ramulator/tprac.yaml` is `prac.yaml` plus the TPRAC plugin,
  so the PRAC plugin, the controller and `abo_threshold: 128` are the ones PRAC
  is measured with (`tests/test_defenses.py` checks this). The PRAC plugin
  already resets the top row of each bank on any RFMab it sees, and still raises
  an ABO if a counter reaches the threshold anyway.

| Parameter | Meaning |
|---|---|
| `tb_rfm_window_ns` | Time between timing-based RFMs. The paper's default is one per tREFI, 3900 ns. Must exceed tRFM (~295 ns). |

The periodic RFMab stalls the rank for tRFM (~295 ns, the same as a refresh), well
under the receiver's 1300 ns back-off band, so the receiver does not mistake
them for back-offs.

## The attack

TPRAC is attacked with PRAC's four programs, unchanged: `defenses.py` builds them
from `attacks/prac/` under PRAC's embedded source names, so `tprac_*` and
`prac_*` are byte-identical. Only the defense differs. A 100 ms window fires no
RFM during a run, which makes it a control that must reproduce PRAC.

## What we measured

Every run's `sim.log` ends with the plugin counters `prac_num_recovery` (ABOs)
and `tprac_num_tb_rfm` (periodic RFMs). They show directly whether the attacker
still triggers the mitigation, independently of how well the receiver decodes.

Proof of concept (`poc --config tprac_window`, 40 bits of `MICRO`, no noise):

| Window (ns) | ABOs | Periodic RFMs | Decoded | Errors |
|---|---|---|---|---|
| 100,000,000 (control) | 18 | 0 | `MICRO` | 0 |
| 31,200 | 15 | 80 | `?ICRO` | 3 |
| 15,600 | 14 | 160 | `~ICRO` | 4 |
| 7,800 | 0 | 322 | `?????` | 18 |
| 3,900 | 0 | 644 | `}????` | 16 |

The control matches PRAC's proof of concept (18 ABOs, `MICRO`). With windows of
15.6 us and longer, the sender still drives a row to 128 activations between two
RFMs and the channel stays open. At 7.8 us and shorter no ABO fires at all, so
nothing the sender does reaches the receiver: it decodes zeros after its first
windows (the few early ones are start-up spikes, not ABOs). The crossover is set
by how many activations the sender can issue between RFMs (about 128 x tRC, ~6 to
12 us here), so it moves with `abo_threshold`.

To reproduce: `poc.run --config tprac_window`, `noise_sweep.run --config tprac`,
then `noise_sweep.plot --config tprac`. The ABO and RFM counts are the
`prac_num_recovery` and `tprac_num_tb_rfm` lines at the end of each `sim.log`.

Noise sweep (`noise_sweep --config tprac`, 100 bytes per pattern, all 36 trials
ok). Capacity is `raw * (1 - H(mean BER))`; ABOs are summed over the four
patterns' baseline runs:

| Window (ns) | ABOs (0x00/0x55/0xAA/0xFF) | Baseline BER | Baseline cap (Kbps) | Noise cap (Kbps) |
|---|---|---|---|---|
| 100,000,000 (control) | 114 / 400 / 400 / 800 | 0.0356 | 30.36 | (PRAC: 13.47) |
| 31,200 | 0 / 366 / 362 / 745 | 0.0387 | 29.79 | - |
| 15,600 | 0 / 336 / 335 / 664 | 0.0912 | 21.82 | - |
| 7,800 | 0 / 0 / 0 / 0 | 0.4709 | 0.10 | - |
| 3,900 | 0 / 0 / 0 / 0 | 0.4378 | 0.44 | 0.14 |

- **The control is PRAC.** Its per-pattern errors (114/0/0/0) and capacity are
  PRAC's to the bit, and its ABO count equals the number of 1 bits sent.
- **PRAC's unexplained 0x00 errors are receiver-triggered ABOs.** With 0x00 the
  sender is idle, yet 114 ABOs fire, exactly the 114 errors: the receiver's own
  probe loop hammers its row past the threshold. TPRAC's RFMs suppress these
  too (0 ABOs at every window from 31,200 ns down).
- **At 7,800 ns and shorter, no ABO fires in any of the 24 trials**, with or
  without noise. Capacity falls from 30.4 to 0.44 Kbps (baseline) and from 13.5
  to 0.14 Kbps (noise), a 98 to 99% reduction.
- **The residue is not TPRAC leaking.** Without ABOs the receiver still sees
  some >1300 ns accesses, presumably periodic RFMs or refreshes lengthened by
  queueing. They are slightly more frequent when the sender hammers (0xFF decodes
  242 windows as 1, 0x00 decodes 147), a memory-contention effect present without
  any mitigation, which is what the remaining ~0.4 Kbps reflects.

## Open questions

1. **Performance.** TPRAC trades bandwidth for closing the channel: at 3900 ns it
   stalls each rank for ~295 ns per 3.9 us (about 7.6% of the time). Measuring
   IPC across windows is the other half of the trade-off.
2. **Threshold.** The crossover window should scale with `abo_threshold`;
   sweeping both would give the window needed for a given threshold.
3. **A many-row attacker.** One RFM mitigates one row per bank. A sender that
   spreads activations over many rows (the paper's wave attack) needs a shorter
   window than this single-row sender; this is untested here.
