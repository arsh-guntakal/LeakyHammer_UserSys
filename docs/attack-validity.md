# Checking that an attack result means something

A BER of 0.5 says the receiver could not decode the sender. It does not say the
defense closes the channel: the sender may never trigger the defense, the
receiver may trigger it itself, the decoder may be blind to the signal, or the
two may be misaligned in time. The DREAM-C result in the original report was
all of these. Before calling a channel closed, check each link below.

## 1. Does the sender trigger the defense?

An access to a row that is already open is a row hit and is not an activation
(the controller uses a closed-row policy with a cap of 16). A real activation
needs a conflicting row in the same bank. The original DREAM-C sender
alternated two rows in *different* banks, so each access was a hit and the
shared counter barely moved. The corrected sender (`attacks/dream/`) cycles a
conflict row per bank so every target access activates.

## 2. Does the receiver trigger it itself?

A receiver that activates rows spread over many counters can fire the defense
in every window, which hides the sender. The corrected DREAM-C receiver probes
rows that avoid the sender's counter entry.

## 3. Can the decoder see the signal?

Periodic refresh (~295 ns) cannot be told from a defense stall by latency, and
gives about five spikes per 20 us window. A fixed spike-count threshold sits
inside that noise. The corrected receivers calibrate: the sender transmits
8 quiet then 8 active windows first, and the threshold is the midpoint of the
two medians. The decoder is still a lower bound on what an attacker can do.

## 4. Are sender and receiver aligned?

The DREAM-C receiver maps thousands of rows before it starts; that took longer
than the sender's start time, so it began ~31 windows late. Both programs now
start at a fixed `DREAM_SYNC_POINT`, and `latency_histogram` records a trial as
failed if the receiver is late.

## The diagnostic

`experiments/latency_histogram` histograms the receiver's probe latencies,
separately for windows where the sender sent 1 and 0. Always run the positive
control (`rfm`) first. One lesson from building it: with a receiver window that
ends too close to the sender's window boundary (500 ns instead of 8 us) the
control showed *no* difference, though RFM is visible. A null result from this
tool means nothing until the control shows one.

Measured with the `default` config (mean probes per window; slow = >= 250 ns):

| Variant | Extra slow probes in a window of 1 |
|---|---|
| RFM (control) | +3.27 |
| RRS, one probed row | +0.25 |
| RRS, 2048 spread rows | -0.40 |
| DREAM-C, default threshold | +1.20 |
| DREAM-C, threshold 8 | +3.77 |

RFM and DREAM-C are visible. The RRS evidence is inconclusive: no excess of slow
probes, though the receiver does complete fewer probes in windows of 1, which
is contention and not a swap. The RRS code was left as it was; this does not
show that the channel is closed or open.
