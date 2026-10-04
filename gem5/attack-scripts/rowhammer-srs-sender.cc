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

#define ROW_COUNT   2

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
const int alloc_size = 64;
DDR5_16Gb_x8 target;

int main(int argc, char *argv[]) {
    if (argc < 4) {
        std::cout << "Usage: " << argv[0] << " <txn_period> <msg_bytes> <data_pattern>" << std::endl;
        return 1;
    }

    uint32_t srs_txn_period = std::atoi(argv[1]);
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

    uint32_t srs_timeout = srs_txn_period - 500;
    std::printf("[SRS-SEND] txn_period: %d msg_bytes: %d data_pattern: %s\n",
                srs_txn_period, msg_bytes, pattern_str.c_str()); FLUSH();

    srand(0xbeef);
    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    // BG=0, Bank=0 — sender's bank. Rows 0 and 1 both map to DCT group 0.
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 0, 0, 0, 0); //EVA

    std::vector<char*> row_ptrs(ROW_COUNT, 0);
    for (int i = 0; i < ROW_COUNT; i++) {
        target.row = i;
        row_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(row_ptrs[i] != MAP_FAILED);
    }

    std::printf("[SRS-SEND] Timeout: %d\n", srs_timeout); FLUSH();

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
    std::printf("[SRS-SEND] Binary: ");
    for (size_t i = 0; i < message.size(); i++) {
        std::printf("%d", static_cast<int>(message[i]));
    }
    std::printf("\n"); FLUSH();

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + srs_txn_period;

    std::printf("[SRS-SEND] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    for (size_t i = 0; i < message.size(); i++) {
        bool bit = message[i];
        if (bit) {
            // Bit=1: hammer to trigger DRFMab (all-bank stall visible to receiver).
            srs_send(row_ptrs, srs_timeout);
        }
        // Bit=0: sleep through window — no hammering, no DRFMab, receiver sees quiet.
        next_window += srs_txn_period;
        min_sleep_assert = std::min<int>(min_sleep_assert, (int)(next_window - m5_rpns()));
        sleep_until(next_window);
    }
    std::printf("[SRS-SEND] MinSleepAssert: %d\n", min_sleep_assert);

    return 0;
}
