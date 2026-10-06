# rfm_prerevert (legacy)

The RFM sender and receiver exactly as they were in commit `2b847b2`, with the
copy of `rowhammer-side.{cc,hh}` and `rowhammer-addr.hh` they were built
against. Files other than `sender.cc` and `receiver.cc` are byte-for-byte what
that commit had (`git show 2b847b2:gem5/attack-scripts/<file>`); the two
programs were named `rowhammer-rfm-sender.cc` and `rowhammer-rfm-receiver.cc`.

**Why it exists.** The report's RFM baseline row (BER 0.000, 48.77 Kbps) was
measured at that commit. It differs from the RFM in `attacks/rfm/` in ways that
were later reverted as broken: latency bands of 8000/6000/2000 ns instead of
1300/550/250 ns, a receiver decision threshold of 1 instead of 3, and (in the
Ramulator timing, see `rfm_prerevert.yaml`) every RFM stall inflated to 5000
cycles. Under those settings the channel decodes every data pattern without
error, but the proof of concept decodes all zeros.

This directory is kept only so the report's numbers can be reproduced. It is not
a model for new defenses; delete it once the report no longer needs it. Built
programs: `rfm_prerevert_sender` and `rfm_prerevert_receiver`.
