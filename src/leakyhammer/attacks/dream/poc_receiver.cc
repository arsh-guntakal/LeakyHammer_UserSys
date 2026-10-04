//
// DREAM-C proof-of-concept covert channel receiver.
//
// Variant of rowhammer-dream-receiver.cc that, instead of comparing each
// received bit against a hex pattern, packs the received bits back into
// ASCII bytes and prints the decoded string.
//
// Usage: dream_poc_receiver <txn_period> <msg_bytes> <data_pattern> [<expected_msg>]
//   - <txn_period>    : window size in ns (must match sender; use 20000).
//   - <msg_bytes>     : kept for argv compatibility, ignored (length is taken
//                       from <expected_msg>).
//   - <data_pattern>  : kept for argv compatibility, ignored.
//   - <expected_msg>  : OPTIONAL. The string the sender is transmitting.
//                       Used to size the receive buffer and to count errors
//                       at the end. Defaults to "UTECE".

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
#include <string>
#include <limits>

#include "rowhammer-addr.hh"
#include "rowhammer-side.hh"

// Spread-row, rate-based decoder (same parameters as the BER-matrix
// dream_receiver). See rowhammer-dream-receiver.cc for the full rationale,
// including how we pick rows under the plugin's RANDOM grouping function
// to (a) span ROW_COUNT distinct DCT entries and (b) avoid colliding with
// the sender's target DCT entry.
#define ROW_COUNT             1024
#define GANG_SIZE             32
#define PROBE_INTERVAL_NS     2000
#define DREAM_DECODE_THRESH   0

#define DREAM_SEED            42
#define DREAM_DCT_ENTRIES     65536
#define DREAM_BANKS_PER_GROUP 4
#define DREAM_BANKS_PER_RANK  32

#define RECV_RANK   1
#define RECV_BG     7
#define RECV_BA     3

#define SENDER_RANK 1
#define SENDER_BG_A 0
#define SENDER_BA_A 0

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
const int alloc_size = 64;
DDR5_16Gb_x8 target;

int main(int argc, char *argv[]) {
    if (argc < 4) {
        std::cout << "Usage: " << argv[0]
                  << " <txn_period> <msg_bytes> <data_pattern> [<expected_msg>]"
                  << std::endl;
        return 1;
    }

    uint32_t dream_txn_period = std::atoi(argv[1]);
    std::string expected_msg = (argc >= 5) ? std::string(argv[4]) : "UTECE";
    int msg_bytes = (int) expected_msg.size();

    // Same 2us margin as the BER-matrix receiver -- see the long comment in
    // rowhammer-dream-receiver.cc for why the older 8us was a bug post-revert.
    uint32_t dream_timeout = dream_txn_period - 2000;

    srand(0xdead);

    // Mirror the BER-matrix receiver: replicate the plugin's mask table,
    // compute the sender's target DCT entry (so we avoid it), and lay out
    // ROW_COUNT distinct probe rows in the receiver's bank.
    auto masks = dream_compute_random_masks(
        DREAM_SEED, NUM_RANKS, DREAM_BANKS_PER_RANK, DREAM_DCT_ENTRIES);
    int recv_bank_idx   = dream_bank_in_rank(RECV_BG, RECV_BA,
                                             DREAM_BANKS_PER_GROUP);
    int sender_bank_idx = dream_bank_in_rank(SENDER_BG_A, SENDER_BA_A,
                                             DREAM_BANKS_PER_GROUP);
    int recv_mask     = masks[RECV_RANK][recv_bank_idx];
    int sender_mask_a = masks[SENDER_RANK][sender_bank_idx];
    int forbidden_recv_row = sender_mask_a ^ recv_mask;

    std::printf("[DREAM-POC-RECV] random_masks: recv(rank=%d,bg=%d,ba=%d -> %d)=%d "
                "sender_dct_idx=%d forbidden_recv_row=%d\n",
                RECV_RANK, RECV_BG, RECV_BA, recv_bank_idx, recv_mask,
                sender_mask_a, forbidden_recv_row); FLUSH();

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
        assert(row_id >= 0 && row_id < DREAM_DCT_ENTRIES);
        target.row = row_id;
        row_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(row_ptrs[i] != MAP_FAILED);
    }
    if (n_replaced > 0) {
        std::printf("[DREAM-POC-RECV] Replaced %d colliding probe row(s) with row %d\n",
                    n_replaced, ROW_COUNT * GANG_SIZE); FLUSH();
    }

    std::printf("[DREAM-POC-RECV] expected_msg: '%s' (%d chars, %d bits)\n",
                expected_msg.c_str(), msg_bytes, msg_bytes * 8);
    std::printf("[DREAM-POC-RECV] spread-row (random grouping): rows=%d gang_size=%d "
                "probe_interval=%dns decode_thresh=%d\n",
                ROW_COUNT, GANG_SIZE, PROBE_INTERVAL_NS, DREAM_DECODE_THRESH);
    std::printf("[DREAM-POC-RECV] Timeout: %d\n", dream_timeout); FLUSH();

    std::vector<bool> message(msg_bytes * 8, false);
    std::vector<int>  spike_counts(msg_bytes * 8, 0);

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + dream_txn_period;

    std::printf("[DREAM-POC-RECV] End of first window: %lu\n", next_window);
    FLUSH();
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

        // Phase-resync (same as BER receiver) -- if we overran a window
        // boundary, skip ahead by an integer number of periods so the next
        // iteration is grid-aligned with the sender's bit clock.
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
    std::printf("[DREAM-POC-RECV] MinSleepAssert: %d\n", min_sleep_assert);
    std::printf("[DREAM-POC-RECV] Resyncs: %d (%d bits skipped)\n",
                n_resyncs, total_skipped_bits);
    std::printf("[DREAM-POC-RECV] Received in %ld ns\n", latency);

    // Print the received binary stream.
    std::printf("[DREAM-POC-RECV] Binary: ");
    for (bool bit : message) {
        std::printf("%d", (int) bit);
    }
    std::printf("\n"); FLUSH();

    // Per-window spike-count histogram & summary (mirrors the BER receiver,
    // for tuning DECODE_THRESH and diagnosing the channel's noise floor).
    int max_count = 0;
    long total_spikes = 0;
    for (int c : spike_counts) {
        if (c > max_count) max_count = c;
        total_spikes += c;
    }
    std::vector<int> hist(max_count + 1, 0);
    for (int c : spike_counts) hist[c]++;
    std::printf("[DREAM-POC-RECV] Spike histogram (count: nWindows): ");
    for (int v = 0; v <= max_count; v++) {
        std::printf("%d:%d ", v, hist[v]);
    }
    std::printf("\n");
    std::printf("[DREAM-POC-RECV] Total spikes: %ld over %zu windows (mean %.2f)\n",
                total_spikes, message.size(),
                (double) total_spikes / (double) message.size());

    // Per-window spike-count trace, aligned with sent bits, for diagnosing
    // whether spike rate is correlated with sender hammering.
    std::printf("[DREAM-POC-RECV] Spike counts: ");
    for (int c : spike_counts) std::printf("%d ", c);
    std::printf("\n"); FLUSH();

    // Repack into ASCII bytes (MSB-first, same as sender) and print.
    std::string decoded;
    decoded.resize(msg_bytes);
    for (int i = 0; i < msg_bytes; i++) {
        char c = 0;
        for (int j = 0; j < 8; j++) {
            c = (c << 1) | (int) message[i * 8 + j];
        }
        decoded[i] = c;
    }

    // Build a human-friendly view: replace non-printable bytes with '?' so
    // a slightly-corrupted decode still shows you what came through.
    std::string visible = decoded;
    for (char& c : visible) {
        if (c < 32 || c > 126) c = '?';
    }

    std::printf("[DREAM-POC-RECV] Decoded ASCII: '%s'\n", visible.c_str());
    std::printf("[DREAM-POC-RECV] Decoded hex  : ");
    for (unsigned char c : decoded) {
        std::printf("%02X ", c);
    }
    std::printf("\n");
    std::printf("[DREAM-POC-RECV] Expected ASCII: '%s'\n", expected_msg.c_str());

    // Bit-level error count.
    int errors = 0;
    for (int i = 0; i < msg_bytes; i++) {
        char expected_c = expected_msg[i];
        for (int j = 0; j < 8; j++) {
            int expected_bit = (expected_c >> (7 - j)) & 1;
            if ((int) message[i * 8 + j] != expected_bit) errors++;
        }
    }
    int char_errors = 0;
    for (int i = 0; i < msg_bytes; i++) {
        if (decoded[i] != expected_msg[i]) char_errors++;
    }
    std::printf("[DREAM-POC-RECV] Bit errors:  %d / %d  (%.2f%%)\n",
                errors, msg_bytes * 8,
                100.0 * errors / (msg_bytes * 8));
    std::printf("[DREAM-POC-RECV] Char errors: %d / %d\n",
                char_errors, msg_bytes);
    FLUSH();

    return 0;
}
