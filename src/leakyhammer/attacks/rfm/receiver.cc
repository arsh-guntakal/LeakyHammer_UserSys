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

#define ROW_COUNT       2
// Match the band-revert in rowhammer-side.hh: with PERIODIC_CAP_NS_RFM=550 and
// ACCESS_CAP_NS=250 the receiver sees ~5-10 RFM events per "1" window, so the
// original artifact's threshold of 3 cleanly separates "1" from background
// noise (~0-2 events per "0" window). e462c3e lowered this to 1 to compensate
// for its inflated latency band; reverting both at once restores the original
// signal-to-noise ratio.
#define ASSERT_THRESH   3

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

    // Leave 8us of margin: rfm_receive's loop check is at the top of each
    // iteration, but a probe already inside the loop can take up to ~7us
    // (an RFM stall) to complete after the timeout has elapsed. Without the
    // margin, nearly every window overruns and the receiver desyncs from the
    // sender's bit clock (manifesting as ~50% BER on alternating patterns).
    uint32_t txn_timeout = txn_period - 8000;

    srand(0xdead);
    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 7, 3, 0, 0);

    std::vector<char*> row_ptrs(ROW_COUNT, nullptr);
    for (int i = 0; i < ROW_COUNT; i++) {
        target.row = i + 1;
        row_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(row_ptrs[i] != MAP_FAILED);
    }

    std::printf("[RECV] Timeout: %d\n", txn_timeout); FLUSH();
    std::vector<bool> message(msg_bytes * 8, -1);
    
    sleep_until(SYNC_POINT);
    uint64_t next_window = m5_rpns() + txn_period;

    std::printf("[RECV] End of first window: %lu\n", next_window); FLUSH();
    int min_sleep_assert = std::numeric_limits<int>::max();
    int n_resyncs = 0;
    int total_skipped_bits = 0;
    uint64_t ns1 = m5_rpns();
    for(size_t i = 0; i < message.size(); i++) {
        message[i] = rfm_receive(row_ptrs, ASSERT_THRESH, txn_timeout);
        next_window += txn_period;
        int slack = (int)(next_window - m5_rpns());
        min_sleep_assert = std::min<int>(min_sleep_assert, slack);

        // Phase-resync: if the receive loop overran by one or more full
        // periods, the receiver is sampling stale bits from the sender's past.
        // Skip ahead by an integer number of periods to re-align with the
        // sender's bit clock; skipped indices are filled with 0.
        uint64_t now = m5_rpns();
        if (now > next_window) {
            uint64_t behind = now - next_window;
            uint64_t skip = (behind + txn_period - 1) / txn_period;
            for (uint64_t s = 0; s < skip && i + 1 < message.size(); s++) {
                ++i;
                message[i] = false;
                ++total_skipped_bits;
            }
            next_window += skip * txn_period;
            ++n_resyncs;
        }
        sleep_until(next_window);
    }
    uint64_t ns2 = m5_rpns();
    uint64_t latency = ns2 - ns1;
    std::printf("[RECV] MinSleepAssert: %d\n", min_sleep_assert); FLUSH();
    std::printf("[RECV] Resyncs: %d (%d bits skipped)\n",
                n_resyncs, total_skipped_bits); FLUSH();

    std::printf("[RECV] Received in %ld ns\n", latency);
    std::printf("[RECV] Binary: ");
    for(bool bit: message) {
        std::printf("%d", (int) bit);
    }
    std::printf("\n"); FLUSH();


    std::vector<int> correct(msg_bytes * 8, 0);
    for (int i = 0; i < msg_bytes * 8; i++) {
        int bit_idx = i % 8;
        correct[i] = (data_pattern >> (7 - bit_idx)) & 1;
    }

    // check how many bits are correct
    int errors = 0;
    for (size_t i = 0; i < message.size(); i++) {
        if (message[i] != correct[i]) {
            errors++;
        }
    }
    std::printf("[RECV] Error rate: %f\n", (errors/(float)message.size())); FLUSH();
    

    return 0;
}

