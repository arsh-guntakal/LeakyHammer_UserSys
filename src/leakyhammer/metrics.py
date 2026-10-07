"""Parsing simulation logs and computing bit error rate and channel capacity.

A transmission simulation prints the bits the sender sent and the bits the
receiver decoded. The covert channel is modelled as a binary symmetric channel,
so its capacity is "raw_rate * (1 - H(BER))", as in the LeakyHammer paper.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

PARSE_ERROR = -30
"""Value of "SimResult.errors" when the log has no sent/received bits."""

LENGTH_MISMATCH = -31
"""Value of "SimResult.errors" when sent and received lengths differ."""

KBPS = 1024.0
"""The paper's Kbps divisor (bits per second / 1024)."""

_SENT = re.compile(r"\[(?:[A-Z]+-)*SEND\] Binary: (\d+)")
_RECEIVED = re.compile(r"\[(?:[A-Z]+-)*RECV\] Binary: (\d+)")
_TIME = re.compile(r"\[(?:[A-Z]+-)*RECV\] Received in (\d+) ns")
_RESYNCS = re.compile(r"\[(?:[A-Z]+-)*RECV\] Resyncs: (\d+)")
_MIN_SLEEP = re.compile(r"\[(?:[A-Z]+-)*RECV\] MinSleepAssert: (-?\d+)")


@dataclass
class SimResult:
    """What one transmission simulation produced.

    - sent (str): bits the sender transmitted, as "0"/"1" characters.
    - received (str): bits the receiver decoded.
    - txn_time_ns (int): simulated time the receiver took, or -1.
    - errors (int): number of differing bits, or a negative failure code
      ("PARSE_ERROR", "LENGTH_MISMATCH"), or -1 if the log does not exist.
    - resyncs (int | None): times the receiver had to resynchronize with the
      sender's bit clock; non-zero means the run is suspect.
    - min_sleep_assert (int | None): smallest slack (ns) before the next
      window; negative means the receiver overran a window.
    """

    sent: str = ""
    received: str = ""
    txn_time_ns: int = -1
    errors: int = -1
    resyncs: Optional[int] = None
    min_sleep_assert: Optional[int] = None

    @property
    def ok(self: "SimResult") -> bool:
        """Returns whether the run produced a usable measurement."""
        return self.errors >= 0


def parse_log(path: Union[str, Path]) -> SimResult:
    """Parses a transmission simulation's log; a missing log is not "ok"."""
    path = Path(path)
    result = SimResult()
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8", errors="replace")
    sent = _SENT.search(text)
    received = _RECEIVED.search(text)
    time = _TIME.search(text)
    resyncs = _RESYNCS.search(text)
    min_sleep = _MIN_SLEEP.search(text)
    result.sent = sent.group(1) if sent else ""
    result.received = received.group(1) if received else ""
    if time:
        result.txn_time_ns = int(time.group(1))
    if resyncs:
        result.resyncs = int(resyncs.group(1))
    if min_sleep:
        result.min_sleep_assert = int(min_sleep.group(1))
    if len(result.sent) != len(result.received):
        result.errors = LENGTH_MISMATCH
    elif not result.sent:
        result.errors = PARSE_ERROR
    else:
        result.errors = sum(
            a != b for a, b in zip(result.sent, result.received)
        )
    return result


def binary_entropy(p: float) -> float:
    """Returns H(p) in bits; 0 at the endpoints, where the limit is 0."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def raw_kbps(msg_bits: int, mean_time_ns: float) -> float:
    """Returns the raw bit rate in Kbps for "msg_bits" sent in the time."""
    return msg_bits / (mean_time_ns / 1e9) / KBPS


def capacity_kbps(raw: float, ber: float) -> float:
    """Returns binary-symmetric-channel capacity: raw * (1 - H(BER))."""
    return raw * (1.0 - binary_entropy(ber))


@dataclass
class Summary:
    """Aggregate of several runs of one configuration.

    - raw_kbps (float): raw bit rate from the mean transmission time.
    - ber (float): mean bit error rate.
    - capacity_kbps (float): capacity computed from the mean BER, as in the
      paper (not the mean of per-run capacities).
    """

    raw_kbps: float
    ber: float
    capacity_kbps: float


def summarize(results: Sequence[SimResult], msg_bits: int) -> Summary:
    """Aggregates runs; raises "ValueError" if any run failed or none exist.

    Failed runs are never averaged in (a crashed run once parsed as a
    negative error count and silently corrupted the mean).
    """
    if not results:
        raise ValueError("No results to summarize")
    failed = [r for r in results if not r.ok]
    if failed:
        raise ValueError(
            f"{len(failed)} of {len(results)} runs failed to produce a "
            f"measurement (errors codes: {sorted({r.errors for r in failed})})"
        )
    mean_time = sum(r.txn_time_ns for r in results) / len(results)
    ber = sum(r.errors for r in results) / len(results) / msg_bits
    raw = raw_kbps(msg_bits, mean_time)
    return Summary(raw, ber, capacity_kbps(raw, ber))


_POC_SENT_MESSAGE = re.compile(r"\[(?:[A-Z]+-)*SEND\] Message: (.+)")
_POC_SENT_TEXT = re.compile(r"message: '([^']*)'")
_POC_WINDOW = re.compile(r"\[(?:[A-Z]+-)*RECV\] Received: ([01]) \(")


@dataclass
class PocResult:
    """What a proof-of-concept transmission produced.

    - sent (str): bits the sender transmitted.
    - received (str): bits the receiver decoded.
    - errors (int): number of differing bits.
    - resyncs (int | None): receiver resynchronizations, if reported.
    """

    sent: str
    received: str
    errors: int
    resyncs: Optional[int] = None

    @property
    def ber(self: "PocResult") -> float:
        """Returns the bit error rate."""
        return self.errors / len(self.sent)

    @property
    def sent_text(self: "PocResult") -> str:
        """Returns the sent bits as text."""
        return bits_to_text(self.sent)

    @property
    def decoded_text(self: "PocResult") -> str:
        """Returns the decoded bits as text ("?" for unprintable bytes)."""
        return bits_to_text(self.received)


def bits_to_text(bits: str) -> str:
    """Returns bits as ASCII, showing unprintable bytes as "?"."""
    chars = [int(bits[i : i + 8], 2) for i in range(0, len(bits), 8)]
    return "".join(chr(c) if 32 <= c < 127 else "?" for c in chars)


def text_to_bits(text: str) -> str:
    """Returns ASCII text as bits, most significant bit first."""
    return "".join(f"{ord(c):08b}" for c in text)


def parse_poc(path: Union[str, Path]) -> PocResult:
    """Parses a proof-of-concept log into sent and decoded bits.

    The receiver prints either one "Binary:" line or one "Received: <bit>"
    line per window; the sent bits come from the sender's "Binary:" line or,
    failing that, from its message text.

    Raises "ValueError" when the log has no usable sent or received bits
    (for example, because the simulation crashed).
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    sent = _SENT.search(text)
    received = _RECEIVED.search(text)
    if sent:
        sent_bits = sent.group(1)
    else:
        message = _POC_SENT_MESSAGE.search(text) or _POC_SENT_TEXT.search(text)
        sent_bits = text_to_bits(message.group(1)) if message else ""
    if received:
        received_bits = received.group(1)
    else:
        received_bits = "".join(_POC_WINDOW.findall(text))
    if not sent_bits or not received_bits:
        raise ValueError(f"{path}: no sent/received bits found")
    if len(sent_bits) != len(received_bits):
        raise ValueError(
            f"{path}: sent {len(sent_bits)} bits, received {len(received_bits)}"
        )
    resyncs = _RESYNCS.search(text)
    return PocResult(
        sent_bits,
        received_bits,
        sum(a != b for a, b in zip(sent_bits, received_bits)),
        int(resyncs.group(1)) if resyncs else None,
    )
