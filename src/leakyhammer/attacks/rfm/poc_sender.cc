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

// This is required on Mac OS X for getting PRI* macros #defined.
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

#define ROW_COUNT           16
#define RFM_TH              40
#define CONFLICT_ROW_IDX    0
#define SHARED_ROW_IDX      1

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
    char data_pattern = std::strtol(argv[3], NULL, 16);
    uint32_t txn_timeout = txn_period - 500;
    std::printf("[SEND] txn_period: %d msg_bytes: %d data_pattern: %d\n", txn_period, msg_bytes, data_pattern); FLUSH();
    srand(0xbeef);
    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 7, 3, 0, 0);

    std::vector<char*> row_ptrs(ROW_COUNT, nullptr);
    for (int i = 0; i < ROW_COUNT; i++) {
        target.row = SHARED_ROW_IDX + i + 1;
        row_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(row_ptrs[i] != MAP_FAILED);
    }

    std::vector<char*> col_ptrs(COLUMN_CAP, nullptr);
    for (int i = 0; i < COLUMN_CAP; i++) {
        target.row = SHARED_ROW_IDX;
        target.column = i;
        col_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(col_ptrs[i] != MAP_FAILED);
    }

    std::printf("[SEND] Timeout: %d\n", txn_timeout); FLUSH();

    // overwrite message with a string
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
    for(size_t i = 0; i < message.size(); i++) {
        std::printf("%d", (int) message[i]);
    }
    std::printf("\n"); FLUSH();

    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + txn_period;

    std::printf("[SEND] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    for(size_t i = 0; i < message.size(); i++) {
        bool bit = message[i];
        std::vector<char*>& target_ptrs = bit ? row_ptrs : col_ptrs;
        if (bit) {
            sidech_stream(target_ptrs, txn_timeout);
        }
        next_window += txn_period;
        min_sleep_assert = std::min<int>(min_sleep_assert, next_window - m5_rpns());
        sleep_until(next_window);
    }
    std::printf("[SEND] MinSleepAssert: %d\n", min_sleep_assert); FLUSH();

    return 0;
}
