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

#include "rowhammer-addr.hh"
#include "rowhammer-side.hh"

#define ROW_COUNT           2
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

    uint32_t prac_txn_period = std::atoi(argv[1]);
    int msg_bytes = std::atoi(argv[2]);
     // The third argument will now be handled as a string.
     std::string pattern_str(argv[3]);

     // Remove the "0x" or "0X" prefix if present.
     if (pattern_str.size() > 1 && pattern_str[0] == '0' &&
        (pattern_str[1] == 'x' || pattern_str[1] == 'X')) {
         pattern_str = pattern_str.substr(2);
     }
 
     // Ensure the string has an even number of characters (each byte is two hex digits)
     if (pattern_str.size() % 2 != 0) {
         pattern_str = "0" + pattern_str;
     }
 
     // Convert the hex string into a vector of bytes.
     std::vector<uint8_t> data_pattern_bytes;
     for (size_t i = 0; i < pattern_str.size(); i += 2) {
         std::string byteString = pattern_str.substr(i, 2);
         uint8_t byte = static_cast<uint8_t>(std::strtoul(byteString.c_str(), nullptr, 16));
         data_pattern_bytes.push_back(byte);
     }
 
    //char data_pattern = std::strtol(argv[3], NULL, 16);
    uint32_t prac_timeout = prac_txn_period - 500;
    std::printf("[SEND] txn_period: %d msg_bytes: %d data_pattern: %s\n", prac_txn_period, msg_bytes, pattern_str.c_str()); FLUSH();

    srand(0xbeef);
    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 7, 3, 0, 0);

    std::vector<char*> row_ptrs(ROW_COUNT, 0);
    for (int i = 0; i < ROW_COUNT; i++) {
        target.row = i;
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

    std::printf("[SEND] Timeout: %d\n", prac_timeout); FLUSH();
    // std::vector<bool> message(msg_bytes * 8, 0);
    // for (int i = 0; i < msg_bytes * 8; i++) {
    //     int bit_idx = i % 8;
    //     message[i] = (data_pattern >> (7 - bit_idx)) & 1;
    // }

    // Convert the pattern bytes to a vector of bits.
    // Each byte is unpacked into bits starting from the most significant bit.
    std::vector<bool> data_pattern_bits;
    for (uint8_t byte : data_pattern_bytes) {
        for (int bit = 7; bit >= 0; bit--) {
            data_pattern_bits.push_back((byte >> bit) & 1);
        }
    }

    // Build the message vector: repeat the data pattern bits until you fill msg_bytes * 8 bits.
    std::vector<bool> message(msg_bytes * 8, 0);
    size_t pattern_size = data_pattern_bits.size();
    for (int i = 0; i < msg_bytes * 8; i++) {
        message[i] = data_pattern_bits[i % pattern_size];
    }
    std::printf("[SEND] Binary: ");
    for(size_t i = 0; i < message.size(); i++) {
        std::printf("%d", static_cast<int>(message[i]));
    }
    std::printf("\n"); FLUSH();

    // int low_sync = (int) PRAC_BACKOFF_THRESH / 2 - 5;
    // int high_sync = (int) PRAC_BACKOFF_THRESH / 2 + 5;
    // prac_synchronize(row_ptrs, low_sync, high_sync, SYNC_ITERS);
    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + prac_txn_period;

    std::printf("[SEND] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    for(size_t i = 0; i < message.size(); i++) {
        bool bit = message[i];
        if (bit) {
            prac_send(row_ptrs, prac_timeout);
        }
        next_window += prac_txn_period;
        min_sleep_assert = std::min<int>(min_sleep_assert, next_window - m5_rpns());
        sleep_until(next_window);
    }
    std::printf("[SEND] MinSleepAssert: %d\n", min_sleep_assert);

    return 0;
}
