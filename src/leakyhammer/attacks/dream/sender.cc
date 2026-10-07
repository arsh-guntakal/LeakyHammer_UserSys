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

// DREAM-C sender for the *random* grouping. The plugin hashes
// (rank, bank, row) -> DCT index as
//
//     bank_in_rank = ba + bg * BANKS_PER_GROUP
//     idx          = (row XOR mask[rank][bank_in_rank]) mod NUM_DCT_ENTRIES
//
// XOR-with-mask is a bijection within a bank, and with vertical_sharing=1
// num_dct_entries == num_rows_per_bank, so two distinct rows in the SAME
// bank can never share a DCT entry. To bump a single counter we have to
// activate two banks at row addresses chosen so that
//
//     row_a XOR mask[rank][bank_a] == row_b XOR mask[rank][bank_b]
//
// We pick row_a = 0 in (BG=0, Ba=0) and row_b = mask[r][A] XOR mask[r][B]
// in (BG=1, Ba=0). Different bankgroups give us tRRD_S between activations
// (vs tRRD_L within a bankgroup), maximizing ACT throughput.
//
// IMPORTANT: these constants must stay in sync with dream.yaml.
//   - DREAM_SEED:      `seed` in the YAML (default 42)
//   - DREAM_DCT_ENTRIES = num_rows_per_bank / vertical_sharing
//                       (DDR5_16Gb_x8 has 65536 rows/bank, ver_sharing=1)
//   - DREAM_BANKS_PER_GROUP, DREAM_BANKS_PER_RANK: from DDR5-VRR's
//     organization preset (BG=8, BA=4 -> 32 banks/rank).
// The plugin prints its mask table at init; grep simulator stdout for
// "[Ramulator::DREAM] random_masks" to verify they match.
#define ROW_COUNT             2
#define DREAM_SEED            42
#define DREAM_DCT_ENTRIES     65536
#define DREAM_BANKS_PER_GROUP 4
#define DREAM_BANKS_PER_RANK  32

// Sender's two banks. Both pinned to rank 1 (matching the original layout
// and the receiver's rank, so the rank-scoped DCT and DRFMab stall are
// shared between sender and receiver).
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
        std::cout << "Usage: " << argv[0] << " <txn_period> <msg_bytes> <data_pattern>" << std::endl;
        return 1;
    }

    uint32_t dream_txn_period = std::atoi(argv[1]);
    int msg_bytes = std::atoi(argv[2]);
    std::string pattern_str(argv[3]);

    // Remove "0x"/"0X" prefix if present.
    if (pattern_str.size() > 1 && pattern_str[0] == '0' &&
        (pattern_str[1] == 'x' || pattern_str[1] == 'X')) {
        pattern_str = pattern_str.substr(2);
    }

    // Ensure even number of hex chars.
    if (pattern_str.size() % 2 != 0) {
        pattern_str = "0" + pattern_str;
    }

    // Convert hex string to bytes.
    std::vector<uint8_t> data_pattern_bytes;
    for (size_t i = 0; i < pattern_str.size(); i += 2) {
        std::string byteString = pattern_str.substr(i, 2);
        uint8_t byte = static_cast<uint8_t>(std::strtoul(byteString.c_str(), nullptr, 16));
        data_pattern_bytes.push_back(byte);
    }

    uint32_t dream_timeout = dream_txn_period - 500;
    std::printf("[DREAM-SEND] txn_period: %d msg_bytes: %d data_pattern: %s\n",
                dream_txn_period, msg_bytes, pattern_str.c_str()); FLUSH();

    srand(0xbeef);

    // Replicate the plugin's mask table to find a colliding row pair under
    // random grouping. See header for the math.
    auto masks = dream_compute_random_masks(
        DREAM_SEED, NUM_RANKS, DREAM_BANKS_PER_RANK, DREAM_DCT_ENTRIES);

    int bank_a_idx = dream_bank_in_rank(SENDER_BG_A, SENDER_BA_A,
                                        DREAM_BANKS_PER_GROUP);
    int bank_b_idx = dream_bank_in_rank(SENDER_BG_B, SENDER_BA_B,
                                        DREAM_BANKS_PER_GROUP);
    int mask_a = masks[SENDER_RANK][bank_a_idx];
    int mask_b = masks[SENDER_RANK][bank_b_idx];

    // Choose row_a = 0; row_b = mask_a XOR mask_b. Both hash to DCT entry
    // mask_a (= 0 XOR mask_a = (mask_a^mask_b) XOR mask_b).
    int row_a = 0;
    int row_b = mask_a ^ mask_b;
    int target_dct_idx = mask_a;  // == row_a XOR mask_a
    std::printf("[DREAM-SEND] random_masks: rank=%d bank_a(bg=%d,ba=%d -> %d)=%d "
                "bank_b(bg=%d,ba=%d -> %d)=%d\n",
                SENDER_RANK,
                SENDER_BG_A, SENDER_BA_A, bank_a_idx, mask_a,
                SENDER_BG_B, SENDER_BA_B, bank_b_idx, mask_b); FLUSH();
    std::printf("[DREAM-SEND] colliding rows: row_a=%d (bg=%d,ba=%d) row_b=%d "
                "(bg=%d,ba=%d) -> shared DCT idx=%d\n",
                row_a, SENDER_BG_A, SENDER_BA_A,
                row_b, SENDER_BG_B, SENDER_BA_B, target_dct_idx); FLUSH();

    // Sanity check: both bank_in_rank values must fall inside [0, 32).
    assert(bank_a_idx >= 0 && bank_a_idx < DREAM_BANKS_PER_RANK);
    assert(bank_b_idx >= 0 && bank_b_idx < DREAM_BANKS_PER_RANK);
    // And row_b must be a valid row id.
    assert(row_b >= 0 && row_b < DREAM_DCT_ENTRIES);

    std::vector<char*> row_ptrs(ROW_COUNT, 0);
    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, SENDER_RANK,
                          SENDER_BG_A, SENDER_BA_A, row_a, 0);
    row_ptrs[0] = (char*) mmap_atk(alloc_size, target.to_physical());
    assert(row_ptrs[0] != MAP_FAILED);

    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, SENDER_RANK,
                          SENDER_BG_B, SENDER_BA_B, row_b, 0);
    row_ptrs[1] = (char*) mmap_atk(alloc_size, target.to_physical());
    assert(row_ptrs[1] != MAP_FAILED);

    std::printf("[DREAM-SEND] Timeout: %d\n", dream_timeout); FLUSH();

    // Unpack pattern bytes into bits (MSB first).
    std::vector<bool> data_pattern_bits;
    for (uint8_t byte : data_pattern_bytes) {
        for (int bit = 7; bit >= 0; bit--) {
            data_pattern_bits.push_back((byte >> bit) & 1);
        }
    }

    // Build message: repeat pattern to fill msg_bytes * 8 bits.
    std::vector<bool> message(msg_bytes * 8, 0);
    size_t pattern_size = data_pattern_bits.size();
    for (int i = 0; i < msg_bytes * 8; i++) {
        message[i] = data_pattern_bits[i % pattern_size];
    }
    std::printf("[DREAM-SEND] Binary: ");
    for (size_t i = 0; i < message.size(); i++) {
        std::printf("%d", static_cast<int>(message[i]));
    }
    std::printf("\n"); FLUSH();

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + dream_txn_period;

    std::printf("[DREAM-SEND] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    for (size_t i = 0; i < message.size(); i++) {
        bool bit = message[i];
        if (bit) {
            // Bit=1: hammer to trigger DRFMab (all-bank stall visible to receiver).
            dream_send_random_gang(row_ptrs, dream_timeout);
        }
        // Bit=0: sleep through window — no hammering, no DRFMab, receiver sees quiet.
        next_window += dream_txn_period;
        min_sleep_assert = std::min<int>(min_sleep_assert, (int)(next_window - m5_rpns()));
        sleep_until(next_window);
    }
    std::printf("[DREAM-SEND] MinSleepAssert: %d\n", min_sleep_assert);

    return 0;
}
