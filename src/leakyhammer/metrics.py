"""Parsing simulation logs and computing bit error rate and channel capacity.

A transmission simulation prints the bits the sender sent and the bits the
receiver decoded. The covert channel is modelled as a binary symmetric channel,
so its capacity is "raw_rate * (1 - H(BER))", as in the LeakyHammer paper.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

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


_TPRAC_WINDOW = re.compile(
    r"\[TPRAC\] window: (\d+) ns = (\d+) clk, first RFM at clk (\d+)"
)
_TPRAC_RFM = re.compile(r"\[TPRAC\] \[(\d+)\] RFMab rank (\d+)")
_NUM_RECOVERY = re.compile(r"prac_num_recovery: (\d+)")
_NUM_TB_RFM = re.compile(r"tprac_num_tb_rfm: (\d+)")
_PRAC_ACT = re.compile(r"\[PRAC\] \[(\d+)\] \[ACT\] Row: (\d+) Act: (\d+)")
_PRAC_RFM = re.compile(r"\[PRAC\] \[(\d+)\] \[RFM\] Row: (\d+) Act: (\d+)")


@dataclass
class TbRfmTrace:
    """The timing-based RFMs a TPRAC run issued (needs the plugin's "debug").

    - window_ns (int): the configured time between RFMs.
    - window_clk (int): the same, in memory-controller clocks.
    - first_clk (int): the clock the first RFM was issued at.
    - rfms (tuple[tuple[int, int], ...]): (clock, rank) of every RFMab.
    - num_recovery (int): Alert Back-Offs PRAC raised ("prac_num_recovery").
    - num_tb_rfm (int): RFMab commands the plugin counted.
    """

    window_ns: int
    window_clk: int
    first_clk: int
    rfms: Tuple[Tuple[int, int], ...]
    num_recovery: int
    num_tb_rfm: int


def parse_tb_rfm_trace(path: Union[str, Path]) -> TbRfmTrace:
    """Parses the TPRAC plugin's debug output and end-of-run counters.

    Raises "ValueError" when the log has no TPRAC header or counters, for
    example because the plugin ran without "debug: true" or gem5 crashed.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    window = _TPRAC_WINDOW.search(text)
    recovery = _NUM_RECOVERY.search(text)
    counted = _NUM_TB_RFM.search(text)
    if not (window and recovery and counted):
        raise ValueError(f"{path}: no TPRAC debug output or counters found")
    rfms = tuple(
        (int(clk), int(rank)) for clk, rank in _TPRAC_RFM.findall(text)
    )
    return TbRfmTrace(
        int(window.group(1)),
        int(window.group(2)),
        int(window.group(3)),
        rfms,
        int(recovery.group(1)),
        int(counted.group(1)),
    )


@dataclass
class RfmResetCheck:
    """Whether every RFM reset the most-activated row of its bank.

    - rfms (int): RFM mitigations the PRAC plugin logged (one per bank).
    - nonzero (int): of those, how many mitigated a row with a count above 1.
    - violations (list[str]): mitigations that broke the rule, each described.
    - desyncs (int): activation lines whose count did not follow the previous
      one for that row; a line clobbered by guest output causes one, and the
      check carries on from the count the log reports.
    """

    rfms: int
    nonzero: int
    violations: List[str]
    desyncs: int


def check_rfm_resets(path: Union[str, Path]) -> RfmResetCheck:
    """Replays PRAC's debug output against the rule for an RFM.

    An RFM must pick a row whose count is the maximum of its bank, report the
    count the activations built up, and leave that row at zero, so its next
    activation counts 1. Needs the PRAC plugin's "debug: true". A count above
    what the log shows is taken as a lost line, not as a violation.
    """
    counts: Dict[int, Dict[int, int]] = {}
    reset: Set[Tuple[int, int]] = set()
    check = RfmResetCheck(0, 0, [], 0)
    for line in (
        Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    ):
        act = _PRAC_ACT.search(line)
        if act:
            bank, row, count = (int(g) for g in act.groups())
            rows = counts.setdefault(bank, {})
            if (bank, row) in reset:
                reset.discard((bank, row))
                if count != 1:
                    check.violations.append(
                        f"bank {bank}: row {row} counts {count} on its first "
                        "activation after an RFM, so the RFM did not reset it"
                    )
            elif count != rows.get(row, 0) + 1:
                check.desyncs += 1
            rows[row] = count
            continue
        rfm = _PRAC_RFM.search(line)
        if not rfm:
            continue
        bank, row, count = (int(g) for g in rfm.groups())
        rows = counts.setdefault(bank, {})
        check.rfms += 1
        check.nonzero += count > 1
        # Counts replayed from the log are lower bounds, because the guest's
        # output can cut an activation line; only what they prove is flagged.
        if count > rows.get(row, 0):
            if row in rows:
                check.desyncs += 1
            rows[row] = count
        elif count < rows.get(row, 0):
            check.violations.append(
                f"bank {bank}: RFM reports {count} for row {row}, which "
                f"was activated {rows[row]} times"
            )
        if rows and count < max(rows.values()):
            check.violations.append(
                f"bank {bank}: RFM took row {row} at {count}, but the "
                f"bank's maximum is {max(rows.values())}"
            )
        rows[row] = 0
        reset.add((bank, row))
    return check


_TIMING = re.compile(r"\[Ramulator::DDR5-VRR\] (n[A-Z]+\d*): (\d+)")
_ABO_TRANSITION = re.compile(
    r"\[PRAC\] \[(\d+)\] <ABOState::(\w+)> -> <ABOState::(\w+)>"
)
_ABO_ASSERT = re.compile(
    r"\[PRAC\] \[(\d+)\] <ABOState::\w+> Asserting ALERT_N"
)
_PRAC_NO_ROW = re.compile(r"\[PRAC\] \[(\d+)\] \[RFM\] No critical row")


def parse_dram_timings(path: Union[str, Path]) -> Dict[str, int]:
    """Returns the DRAM timings (in clocks) a run printed at start-up.

    Raises "ValueError" when the log has none, for example when it comes from
    a build older than the print.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    timings = {name: int(v) for name, v in _TIMING.findall(text)}
    if not timings:
        raise ValueError(f"{path}: no DRAM timings found")
    return timings


@dataclass
class AboEpisode:
    """One Alert Back-Off, from the alert to the end of the delay.

    - trigger_count (int): the count of the activation just before the alert.
    - assert_clk, recovery_clk, delay_clk, normal_clk (int): clocks of the
      alert, the start of the RFM recovery, the start of the delay, and the
      return to normal operation.
    - window_acts (int): activations between the alert and the recovery.
    - recovery_mitigations (int): per-bank mitigations the recovery logged.
    - recovery_max_count (int): largest count among them.
    - delay_acts (int): activations the delay lasted for.
    """

    trigger_count: int
    assert_clk: int
    recovery_clk: int
    delay_clk: int
    normal_clk: int
    window_acts: int
    recovery_mitigations: int
    recovery_max_count: int
    delay_acts: int


@dataclass
class AboTrace:
    """The back-offs a PRAC run raised (needs PRAC's "debug: true").

    - episodes (list[AboEpisode]): back-offs seen from alert to the end.
    - incomplete (int): alerts whose lines were cut or that the run ended in.
    - max_count_before_first (int): the highest count of any row before the
      first alert (0 when there was none).
    """

    episodes: List[AboEpisode]
    incomplete: int
    max_count_before_first: int


def parse_abo_trace(path: Union[str, Path]) -> AboTrace:
    """Replays PRAC's debug output into back-off episodes.

    The plugin handles a command's state change before it counts the command,
    so the last activation of the delay and the last RFM of the recovery are
    logged just after the transition they cause; the counts below allow for
    that (the delay's closing activation is added, and the recovery's RFM
    lines are read up to the first activation after it starts).
    """
    lines = (
        Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    )
    episodes: List[AboEpisode] = []
    incomplete = 0
    max_before_first = 0
    last_count = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        act = _PRAC_ACT.search(line)
        if act:
            last_count = int(act.group(3))
            if not episodes and not incomplete:
                max_before_first = max(max_before_first, last_count)
            i += 1
            continue
        alert = _ABO_ASSERT.search(line)
        if not alert:
            i += 1
            continue
        episode, i = _read_abo_episode(lines, i, last_count)
        if episode is None:
            incomplete += 1
        else:
            episodes.append(episode)
    return AboTrace(episodes, incomplete, max_before_first)


def _read_abo_episode(
    lines: List[str], start: int, trigger: int
) -> Tuple[Optional[AboEpisode], int]:
    """Reads one episode from the alert line; returns it and the next line."""
    marks: Dict[str, int] = {}
    window_acts = delay_acts = mitigations = max_count = 0
    phase = "NORMAL"
    alert_clk = int(_ABO_ASSERT.search(lines[start]).group(1))  # type: ignore[union-attr]
    i = start + 1
    while i < len(lines):
        line = lines[i]
        i += 1
        move = _ABO_TRANSITION.search(line)
        if move:
            clk, before, after = (
                int(move.group(1)),
                move.group(2),
                move.group(3),
            )
            if before != phase:
                return None, i
            marks[after] = clk
            phase = after
            if after == "NORMAL":
                return (
                    AboEpisode(
                        trigger,
                        alert_clk,
                        marks.get("RECOVERY", -1),
                        marks.get("DELAY", -1),
                        clk,
                        window_acts,
                        mitigations,
                        max_count,
                        delay_acts + 1,
                    ),
                    i,
                )
            continue
        if _PRAC_ACT.search(line):
            if phase == "PRE_RECOVERY":
                window_acts += 1
            elif phase == "DELAY":
                delay_acts += 1
            elif phase == "RECOVERY":
                # An activation inside the recovery is a lost RFM line.
                return None, i
            continue
        rfm = _PRAC_RFM.search(line)
        if rfm and phase in ("RECOVERY", "DELAY") and delay_acts == 0:
            mitigations += 1
            max_count = max(max_count, int(rfm.group(3)))
        elif _PRAC_NO_ROW.search(line) and phase in ("RECOVERY", "DELAY"):
            if delay_acts == 0:
                mitigations += 1
    return None, i


def parse_counter(path: Union[str, Path], name: str) -> int:
    """Returns a plugin counter printed at the end of a run.

    "name" is the counter's name in the log, for example "prac_num_recovery".

    Raises "ValueError" when the log has no such counter.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    found = re.search(rf"^\s*{re.escape(name)}: (\d+)", text, re.MULTILINE)
    if not found:
        raise ValueError(f"{path}: no counter '{name}'")
    return int(found.group(1))
