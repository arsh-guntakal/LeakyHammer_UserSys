// Copyright 2015, Google, Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#define __STDC_FORMAT_MACROS

#include <assert.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <iostream>
#include <vector>

#include "rowhammer-addr.hh"
#include "rowhammer-side.hh"

// DREAM-C v2 receiver (random grouping): spread-row, rate-based decoder.
//
// Why: a single-row receiver crosses DREAM's threshold on its own, which
// makes its self-triggered DRFMab events indistinguishable from the
// sender's. We allocate ROW_COUNT rows that each hash to a DISTINCT DCT
// entry under the plugin's random grouping function, then round-robin
// probe over them. This divides the receiver's per-DCT-entry ACT rate by
// ROW_COUNT, which is what keeps the receiver below threshold.
//
// Under random grouping, picking rows {0, GANG_SIZE, 2*GANG_SIZE, ...}
// already gives ROW_COUNT distinct DCT entries (XOR-with-mask is a
// bijection, and `i*GANG_SIZE` for i in [0, ROW_COUNT) are distinct).
// What matters is the SECOND constraint that random grouping introduces:
// the receiver MUST avoid the DCT entry the sender is hammering. We
// compute the sender's entry from the replicated mask table and skip any
// receiver row that would collide with it, replacing it with a row past
// the end of the candidate window.
//
// Decoding is rate-based: count DRFMab-class latency spikes per window
// and classify "1" if count > DREAM_DECODE_THRESH.
//
// IMPORTANT: keep DREAM_SEED, DREAM_DCT_ENTRIES, and DREAM_BANKS_PER_*
// in sync with dream.yaml + DDR5-VRR's organization. Mirror of the same
// constants in rowhammer-dream-sender.cc.
#define ROW_COUNT             1024
#define GANG_SIZE             32      // row spacing; arbitrary so long as it gives distinct DCT entries
#define PROBE_INTERVAL_NS     2000    // 2us spacing -> ~10 probes per 20us window
#define DREAM_DECODE_THRESH   0       // per-window spike count to decode "1" (>0 spikes)

#define DREAM_SEED            42
#define DREAM_DCT_ENTRIES     65536
#define DREAM_BANKS_PER_GROUP 4
#define DREAM_BANKS_PER_RANK  32

// Receiver's bank. Pinned to rank 1 so the rank-scoped DCT and DRFMab
// stall are shared with the sender.
#define RECV_RANK   1
#define RECV_BG     7
#define RECV_BA     3

// Sender's bank A (the one with row=0). Used to compute the sender's
// target DCT index so we can avoid colliding with it.
#define SENDER_RANK 1
#define SENDER_BG_A 0
#define SENDER_BA_A 0

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
const int alloc_size = 64;
DDR5_16Gb_x8 target;

int main(int argc, char *argv[]) {
    if (argc < 4) {
        std::cout << "Usage: " << argv[0] << " <txn_period> <msg_bytes> <data_pattern>" << std::endl;
        return 1;
    }

    uint32_t dream_txn_period = std::atoi(argv[1]);
    int msg_bytes = std::atoi(argv[2]);
    char data_pattern = std::strtol(argv[3], NULL, 16);
    // Receiver listens for (txn_period - 2000) ns per window. The 2us margin
    // covers the worst-case overrun: a probe in flight when timeout elapses
    // (a DRFMab stall is ~280ns post-revert, plus probe overhead) and a few
    // hundred ns of CPU jitter. Empirically 1us is borderline (-366ns
    // overruns triggered 20 resyncs in a 40-bit POC); 2us is safe.
    //
    // We previously used 8000 here -- a leftover from the e462c3e timing
    // regime when DRFMab stalls were ~7 us. With DDR5-VRR.cpp reverted to
    // JEDEC formulas DRFMab is back to ~280 ns, and an 8 us margin was a
    // bug: the matrix sender hammers for (txn_period - 500) = 19500 ns, so
    // sender events from the last 7 us of every "1" window leaked into the
    // receiver's NEXT window (which was sleeping for those 7 us). The
    // leakage gave false-positive spikes on "0" windows -- exactly the
    // misaligned bit pattern we observed before this fix.
    uint32_t dream_timeout = dream_txn_period - 2000;

    srand(0xdead);

    // Replicate the plugin's mask table to compute (a) our own bank's
    // mask -- so we know what DCT entries our probe rows hash to -- and
    // (b) the sender's target DCT entry, so we can avoid colliding with
    // it.
    auto masks = dream_compute_random_masks(
        DREAM_SEED, NUM_RANKS, DREAM_BANKS_PER_RANK, DREAM_DCT_ENTRIES);

    int recv_bank_idx   = dream_bank_in_rank(RECV_BG, RECV_BA,
                                             DREAM_BANKS_PER_GROUP);
    int sender_bank_idx = dream_bank_in_rank(SENDER_BG_A, SENDER_BA_A,
                                             DREAM_BANKS_PER_GROUP);
    int recv_mask     = masks[RECV_RANK][recv_bank_idx];
    int sender_mask_a = masks[SENDER_RANK][sender_bank_idx];

    // Sender hammers (row_a=0 in bank_a, row_b=mask_a^mask_b in bank_b),
    // both hashing to DCT entry sender_mask_a. The receiver's row r in its
    // bank hashes to (r XOR recv_mask). Avoid r such that
    //     r XOR recv_mask == sender_mask_a
    // i.e. r == sender_mask_a XOR recv_mask.
    int forbidden_recv_row = sender_mask_a ^ recv_mask;

    std::printf("[DREAM-RECV] random_masks: recv(rank=%d,bg=%d,ba=%d -> %d)=%d "
                "sender_a(rank=%d,bg=%d,ba=%d -> %d)=%d "
                "sender_dct_idx=%d forbidden_recv_row=%d\n",
                RECV_RANK, RECV_BG, RECV_BA, recv_bank_idx, recv_mask,
                SENDER_RANK, SENDER_BG_A, SENDER_BA_A, sender_bank_idx,
                sender_mask_a, sender_mask_a, forbidden_recv_row); FLUSH();

    // Allocate ROW_COUNT rows at row IDs {0, GANG_SIZE, 2*GANG_SIZE, ...},
    // skipping any candidate that would collide with the sender's DCT
    // entry. We replace a forbidden candidate with row ROW_COUNT*GANG_SIZE
    // (the next slot past the end of the nominal window). This keeps all
    // ROW_COUNT rows distinct AND none of them collide with the sender.
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, RECV_RANK,
                          RECV_BG, RECV_BA, 0, 0);

    std::vector<char*> row_ptrs(ROW_COUNT, 0);
    int n_replaced = 0;
    for (int i = 0; i < ROW_COUNT; i++) {
        int row_id = i * GANG_SIZE;
        if (row_id == forbidden_recv_row) {
            row_id = ROW_COUNT * GANG_SIZE;
            n_replaced++;
        }
        // Defensive: row_id must be a valid DDR5_16Gb_x8 row.
        assert(row_id >= 0 && row_id < DREAM_DCT_ENTRIES);
        target.row = row_id;
        row_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(row_ptrs[i] != MAP_FAILED);
    }
    if (n_replaced > 0) {
        std::printf("[DREAM-RECV] Replaced %d colliding probe row(s) with row %d\n",
                    n_replaced, ROW_COUNT * GANG_SIZE); FLUSH();
    }

    std::printf("[DREAM-RECV] v2 spread-row (random grouping): rows=%d, gang_size=%d, probe_interval=%dns, decode_thresh=%d\n",
                ROW_COUNT, GANG_SIZE, PROBE_INTERVAL_NS, DREAM_DECODE_THRESH); FLUSH();
    std::printf("[DREAM-RECV] Timeout: %d\n", dream_timeout); FLUSH();
    std::vector<bool> message(msg_bytes * 8, false);
    std::vector<int> spike_counts(msg_bytes * 8, 0);

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + dream_txn_period;

    std::printf("[DREAM-RECV] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    int n_resyncs = 0;
    int total_skipped_bits = 0;
    uint64_t ns1 = m5_rpns();
    for (size_t i = 0; i < message.size(); i++) {
        int n_spikes = dream_receive_count_random_gang(row_ptrs, dream_timeout, PROBE_INTERVAL_NS);
        spike_counts[i] = n_spikes;
        message[i] = (n_spikes > DREAM_DECODE_THRESH);
        next_window += dream_txn_period;
        int slack = (int)(next_window - m5_rpns());
        min_sleep_assert = std::min<int>(min_sleep_assert, slack);

        // Phase-resync: if the receive loop overran the next window boundary by
        // one or more full periods, the receiver is sampling stale bits from
        // the sender's past. Skip ahead by an integer number of periods so the
        // next iteration is grid-aligned with the sender's bit clock again.
        // The skipped indices are filled with 0 (we couldn't observe them).
        uint64_t now = m5_rpns();
        if (now > next_window) {
            uint64_t behind = now - next_window;
            uint64_t skip = (behind + dream_txn_period - 1) / dream_txn_period;
            for (uint64_t s = 0; s < skip && i + 1 < message.size(); s++) {
                ++i;
                message[i] = false;
                spike_counts[i] = -1;
                ++total_skipped_bits;
            }
            next_window += skip * dream_txn_period;
            ++n_resyncs;
        }
        sleep_until(next_window);
    }
    uint64_t ns2 = m5_rpns();
    uint64_t latency = ns2 - ns1;
    std::printf("[DREAM-RECV] MinSleepAssert: %d\n", min_sleep_assert);
    std::printf("[DREAM-RECV] Resyncs: %d (%d bits skipped)\n",
                n_resyncs, total_skipped_bits);

    std::printf("[DREAM-RECV] Received in %ld ns\n", latency);
    std::printf("[DREAM-RECV] Binary: ");
    for (bool bit : message) {
        std::printf("%d", (int) bit);
    }
    std::printf("\n"); FLUSH();

    // Per-window spike-count histogram & summary (for tuning DECODE_THRESH).
    int max_count = 0;
    long total_spikes = 0;
    for (int c : spike_counts) {
        if (c > max_count) max_count = c;
        total_spikes += c;
    }
    std::vector<int> hist(max_count + 1, 0);
    for (int c : spike_counts) hist[c]++;
    std::printf("[DREAM-RECV] Spike histogram (count: nWindows): ");
    for (int v = 0; v <= max_count; v++) {
        std::printf("%d:%d ", v, hist[v]);
    }
    std::printf("\n");
    std::printf("[DREAM-RECV] Total spikes: %ld over %zu windows (mean %.2f)\n",
                total_spikes, message.size(),
                (double)total_spikes / (double)message.size());
    FLUSH();

    // Compare against expected pattern.
    std::vector<int> correct(msg_bytes * 8, 0);
    for (int i = 0; i < msg_bytes * 8; i++) {
        int bit_idx = i % 8;
        correct[i] = (data_pattern >> (7 - bit_idx)) & 1;
    }

    int errors = 0;
    for (size_t i = 0; i < message.size(); i++) {
        if ((int)message[i] != correct[i]) {
            errors++;
        }
    }
    std::printf("[DREAM-RECV] Errors: %d / %d\n", errors, msg_bytes * 8);
    std::printf("[DREAM-RECV] Error rate: %f\n", (errors / (float)message.size())); FLUSH();

    return 0;
}
