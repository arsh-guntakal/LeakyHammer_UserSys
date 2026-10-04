// Copyright 2015, Google, Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// DREAM-C proof-of-concept covert channel sender.
//
// Variant of rowhammer-dream-sender.cc that, instead of repeating a single
// hex byte, transmits a literal ASCII string (default "UTECE") as MSB-first
// bits. Receiver counterpart: dream-poc-receiver.cc.
//
// Usage: dream_poc_sender <txn_period> <msg_bytes> <data_pattern> [<message>]
//   - <txn_period>   : window size in ns (use 20000 to match the BER matrix).
//   - <msg_bytes>    : kept for argv compatibility with the BER framework, ignored.
//   - <data_pattern> : same, ignored.
//   - <message>      : OPTIONAL ASCII string to transmit. Defaults to "UTECE".
//
// The receiver derives msg_bytes from its own copy of the expected message,
// so sender and receiver MUST use the same string.
//
// Mirrors rowhammer-dream-sender.cc's collision-targeted two-bank layout for
// the plugin's random grouping function. See that file's header for the math.

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

// Two-bank colliding-row sender for the plugin's RANDOM grouping function.
// See rowhammer-dream-sender.cc for the full rationale; tl;dr: under random
// grouping (XOR-with-mask), two rows in the SAME bank can never share a DCT
// entry, so we have to ACT from two different banks at row addresses chosen
// to XOR through different masks to the same DCT index.
#define ROW_COUNT             2
#define DREAM_SEED            42
#define DREAM_DCT_ENTRIES     65536
#define DREAM_BANKS_PER_GROUP 4
#define DREAM_BANKS_PER_RANK  32

#define SENDER_RANK   1
#define SENDER_BG_A   0
#define SENDER_BA_A   0
#define SENDER_BG_B   1
#define SENDER_BA_B   0

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
const int alloc_size = 64;
DDR5_16Gb_x8 target;

int main(int argc, char *argv[]) {
    if (argc < 4) {
        std::cout << "Usage: " << argv[0]
                  << " <txn_period> <msg_bytes> <data_pattern> [<message>]"
                  << std::endl;
        return 1;
    }

    uint32_t dream_txn_period = std::atoi(argv[1]);

    std::string message_string = (argc >= 5) ? std::string(argv[4]) : "UTECE";

    uint32_t dream_timeout = dream_txn_period - 500;
    std::printf("[DREAM-POC-SEND] txn_period: %d msg_chars: %zu message: '%s'\n",
                dream_txn_period, message_string.size(), message_string.c_str());
    FLUSH();

    srand(0xbeef);

    // Replicate the plugin's mask table to compute a colliding row pair.
    auto masks = dream_compute_random_masks(
        DREAM_SEED, NUM_RANKS, DREAM_BANKS_PER_RANK, DREAM_DCT_ENTRIES);

    int bank_a_idx = dream_bank_in_rank(SENDER_BG_A, SENDER_BA_A,
                                        DREAM_BANKS_PER_GROUP);
    int bank_b_idx = dream_bank_in_rank(SENDER_BG_B, SENDER_BA_B,
                                        DREAM_BANKS_PER_GROUP);
    int mask_a = masks[SENDER_RANK][bank_a_idx];
    int mask_b = masks[SENDER_RANK][bank_b_idx];

    int row_a = 0;
    int row_b = mask_a ^ mask_b;
    int target_dct_idx = mask_a;
    std::printf("[DREAM-POC-SEND] random_masks: rank=%d bank_a(bg=%d,ba=%d -> %d)=%d "
                "bank_b(bg=%d,ba=%d -> %d)=%d\n",
                SENDER_RANK,
                SENDER_BG_A, SENDER_BA_A, bank_a_idx, mask_a,
                SENDER_BG_B, SENDER_BA_B, bank_b_idx, mask_b); FLUSH();
    std::printf("[DREAM-POC-SEND] colliding rows: row_a=%d (bg=%d,ba=%d) row_b=%d "
                "(bg=%d,ba=%d) -> shared DCT idx=%d\n",
                row_a, SENDER_BG_A, SENDER_BA_A,
                row_b, SENDER_BG_B, SENDER_BA_B, target_dct_idx); FLUSH();

    assert(bank_a_idx >= 0 && bank_a_idx < DREAM_BANKS_PER_RANK);
    assert(bank_b_idx >= 0 && bank_b_idx < DREAM_BANKS_PER_RANK);
    assert(row_b >= 0 && row_b < DREAM_DCT_ENTRIES);

    std::vector<char*> row_ptrs(ROW_COUNT, 0);
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, SENDER_RANK,
                          SENDER_BG_A, SENDER_BA_A, row_a, 0);
    row_ptrs[0] = (char*) mmap_atk(alloc_size, target.to_physical());
    assert(row_ptrs[0] != MAP_FAILED);

    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, SENDER_RANK,
                          SENDER_BG_B, SENDER_BA_B, row_b, 0);
    row_ptrs[1] = (char*) mmap_atk(alloc_size, target.to_physical());
    assert(row_ptrs[1] != MAP_FAILED);

    std::printf("[DREAM-POC-SEND] Timeout: %d\n", dream_timeout); FLUSH();

    // Encode the ASCII string as MSB-first bits.
    std::vector<bool> message(message_string.size() * 8, 0);
    for (size_t i = 0; i < message_string.size(); i++) {
        char c = message_string[i];
        for (int j = 0; j < 8; j++) {
            message[i * 8 + j] = (c >> (7 - j)) & 1;
        }
    }

    std::printf("[DREAM-POC-SEND] Binary: ");
    for (size_t i = 0; i < message.size(); i++) {
        std::printf("%d", (int) message[i]);
    }
    std::printf("\n"); FLUSH();

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + dream_txn_period;

    std::printf("[DREAM-POC-SEND] End of first window: %lu\n", next_window);
    FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    for (size_t i = 0; i < message.size(); i++) {
        bool bit = message[i];
        if (bit) {
            // Bit=1: hammer to push the gang counter past T_TH and trigger
            // DRFMab, producing an all-bank stall the receiver can detect.
            dream_send_random_gang(row_ptrs, dream_timeout);
        }
        // Bit=0: idle through window -- no hammering, no DRFMab, receiver
        // sees a quiet window.
        next_window += dream_txn_period;
        min_sleep_assert = std::min<int>(min_sleep_assert,
                                         (int)(next_window - m5_rpns()));
        sleep_until(next_window);
    }
    std::printf("[DREAM-POC-SEND] MinSleepAssert: %d\n", min_sleep_assert);
    FLUSH();

    return 0;
}
