"""Decode a POC log: print the sent/decoded text and bit errors.

Usage: python3 result-scripts/decode_poc.py results/poc/<name>.txt
Handles the RFM/RRS per-window "Received: <bit> (<n> ...)" lines and the
DREAM POC's single "Binary:" line.
"""
import re
import sys

text = open(sys.argv[1], errors="replace").read()

sent = re.search(r"SEND\] Binary: ([01]+)", text)
# DREAM's POC prints one "RECV] Binary:" line; RFM/RRS print one line per window.
full = re.search(r"RECV\] Binary: ([01]+)", text)
windows = re.findall(r"RECV\] Received: ([01]) \(", text)
if not sent or not (full or windows):
    sys.exit(f"could not find sent/received bits in {sys.argv[1]} (did the run crash?)")
sent = sent.group(1)
recv = full.group(1) if full else "".join(windows)

def to_text(b):
    chars = [int(b[i:i + 8], 2) for i in range(0, len(b), 8)]
    return "".join(chr(c) if 32 <= c < 127 else "?" for c in chars)

errors = sum(a != b for a, b in zip(sent, recv))
print(f"sent    : {to_text(sent)!r}")
print(f"decoded : {to_text(recv)!r}")
print(f"errors  : {errors}/{len(sent)}  (BER {errors / len(sent):.3f})")
resyncs = re.search(r"Resyncs: (\d+)", text)
if resyncs:
    print(f"resyncs : {resyncs.group(1)}")
