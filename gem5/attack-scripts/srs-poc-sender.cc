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
#include <limits>

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

    uint32_t txn_period = std::atoi(argv[1]);
    int msg_bytes = std::atoi(argv[2]);
    uint32_t txn_timeout = txn_period - 500;

    std::printf("[SEND] txn_period: %d msg_bytes: %d\n", txn_period, msg_bytes); FLUSH();

    srand(0xbeef);
    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 0, 0, 0, 0);

    std::vector<char*> row_ptrs(ROW_COUNT, nullptr);
    for (int i = 0; i < ROW_COUNT; i++) {
        target.row = i;
        row_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(row_ptrs[i] != MAP_FAILED);
    }

    std::printf("[SEND] Timeout: %d\n", txn_timeout); FLUSH();

    std::string message_string = "MICRO";
    std::vector<bool> message(message_string.size() * 8, 0);
    for (size_t i = 0; i < message_string.size(); i++) {
        char c = message_string[i];
        for (int j = 0; j < 8; j++) {
            message[i * 8 + j] = (c >> (7 - j)) & 1;
        }
    }
    std::printf("[SEND] Message: %s\n", message_string.c_str()); FLUSH();

    std::printf("[SEND] Binary: ");
    for (bool bit : message) {
        std::printf("%d", (int) bit);
    }
    std::printf("\n"); FLUSH();

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + txn_period;

    std::printf("[SEND] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    for (size_t i = 0; i < message.size(); i++) {
        bool bit = message[i];
        if (bit) {
            srs_send(row_ptrs, txn_timeout);
        }
        // bit=0: idle, no hammering, receiver sees no swap
        next_window += txn_period;
        min_sleep_assert = std::min<int>(min_sleep_assert, (int)(next_window - m5_rpns()));
        sleep_until(next_window);
    }
    std::printf("[SEND] MinSleepAssert: %d\n", min_sleep_assert); FLUSH();

    return 0;
}
