// Shared by the DREAM-C sender and receiver programs (matrix and proof of concept).
//
// Three things make this attack work against DREAM-C, each fixing a way the
// earlier version could not see a channel that was there:
//
//  1. The sender needs real activations. The memory controller keeps a row open
//     for up to 16 column accesses, so alternating between two rows in two
//     DIFFERENT banks (as random grouping forces) makes every access a row hit
//     and almost no ACTs (about 19 per 20 us window, against 214 accesses). The
//     sender therefore interleaves a conflict row in each bank, which closes
//     the target row between accesses and makes each target access an ACT.
//  2. The receiver must not trigger DRFMab itself. It cycles through many
//     distinct rows (so none reaches the threshold) and probes continuously.
//  3. A DRFMab stall (about 280 ns) is almost as long as a periodic refresh
//     (about 295 ns), so latency cannot tell them apart; only their count can.
//     A window holds about 5 refresh spikes, so "any spike means 1" is
//     meaningless. A short training preamble (quiet windows, then windows of
//     1s) lets the receiver set the threshold between the two observed levels.
#ifndef DREAM_ATTACK_HH_
#define DREAM_ATTACK_HH_

#include <algorithm>
#include <stdint.h>
#include <vector>

#include "rowhammer-addr.hh"
#include "rowhammer-side.hh"

// Both sides start at this time. It must come after the receiver has mapped its
// 16384 probe rows (about 850 us); the shared SYNC_POINT (220 us) does not, and
// the receiver then starts tens of windows late and decodes garbage.
#define DREAM_SYNC_POINT        1500000

#define DREAM_QUIET_WINDOWS     8   // training: windows with no hammering
#define DREAM_ACTIVE_WINDOWS    8   // training: windows of hammering (1s)
#define DREAM_PREAMBLE_WINDOWS  (DREAM_QUIET_WINDOWS + DREAM_ACTIVE_WINDOWS)

#define DREAM_PROBE_ROWS        16384  // distinct receiver rows (one DCT entry each)
#define DREAM_PROBE_ROW_STRIDE  4      // 16384 * 4 = the 65536 rows of a bank
#define DREAM_CONFLICT_ROWS     16     // conflict rows per sender bank

// What the sender transmits in window "w" of a message of "msg_bits" bits.
inline bool dream_window_bit(int w, const std::vector<bool>& message) {
    if (w < DREAM_PREAMBLE_WINDOWS) return w >= DREAM_QUIET_WINDOWS;
    return message[w - DREAM_PREAMBLE_WINDOWS];
}

// Median of the non-negative entries of "v" in [begin, end); -1 marks a window
// the receiver skipped. Returns -1 if there is none.
inline double dream_median(const std::vector<int>& v, int begin, int end) {
    std::vector<int> kept;
    for (int i = begin; i < end; i++) if (v[i] >= 0) kept.push_back(v[i]);
    if (kept.empty()) return -1;
    std::sort(kept.begin(), kept.end());
    size_t n = kept.size();
    return n % 2 ? kept[n / 2] : (kept[n / 2 - 1] + kept[n / 2]) / 2.0;
}

// Threshold between the quiet and the active training windows: the midpoint of
// their medians. A window decodes as 1 if its spike count is above it.
inline double dream_threshold(const std::vector<int>& counts) {
    double quiet = dream_median(counts, 0, DREAM_QUIET_WINDOWS);
    double active = dream_median(counts, DREAM_QUIET_WINDOWS,
                                 DREAM_PREAMBLE_WINDOWS);
    return (quiet + active) / 2.0;
}

// Hammer one counter for "timeout" ns: access each target row, each followed
// by a conflict row in the same bank, so every target access is an ACT.
inline void dream_conflict_hammer(char* target_a, char* target_b,
                                  const std::vector<char*>& conflict_a,
                                  const std::vector<char*>& conflict_b,
                                  uint32_t timeout) {
    uint64_t start = m5_rpns();
    size_t k = 0;
    while (m5_rpns() - start < timeout) {
        char* sequence[4] = {target_a, conflict_a[k % conflict_a.size()],
                             target_b, conflict_b[k % conflict_b.size()]};
        k++;
        for (char* row : sequence) {
            asm volatile("clflush (%0)" : : "r" (row) : "memory");
            *(volatile char*)row;
        }
    }
}

#endif  // DREAM_ATTACK_HH_
