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

#include <gem5/m5ops.h>
#include <iostream>
#include <vector>
#include <random>

#include "rowhammer-addr.hh"
#include "rowhammer-side.hh"

#define FLUSH()         fflush(stdout)
#define SYS_MMAP_ATK    451
#define BACKOFF_THRESH  128
#define SETUP_THRESH    64
#define REF_WINDOW_NS   32'000'000

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
DDR5_16Gb_x8 target;
const int alloc_size = 64;

int stream = 0;
int incr = 64;

int main(int argc, char *argv[]) {
    if (argc < 4) {
        std::cout << "Usage: " << argv[0] << " <attack_period> <row_idx> <access_rate> [row_count]" << std::endl;
        return 1;
    }

    int iterations = 1000000;
    uint64_t attack_period = (std::atoi(argv[1]) + SYNC_POINT);
    int row_idx = std::atoi(argv[2]);
    int access_rate = std::atoi(argv[3]);

    iterations = attack_period / (access_rate + 100);


    int row_count = 1;
    if (argc == 5) {
        row_count = std::atoi(argv[4]);
    }

    int access_noise = access_rate * 0.1f;

    std::mt19937 generator;
    std::uniform_int_distribution<uint32_t> distribution(access_rate - access_noise, access_rate + access_noise);

    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 7, 3, row_idx, 31);

    std::vector<char*> target_ptrs(row_count, 0);

    for (int i = 0; i < row_count; i++) {
        target.row = row_idx + i;
        target_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(target_ptrs[i] != MAP_FAILED);
    }
    std::printf("[MRNOISE] Access Rate (ns): %d\n", access_rate); FLUSH();

    sleep_until(SYNC_POINT);
    uint64_t start = m5_rpns();
    uint64_t end = 0;
    for (int i = 0; i < iterations; i++) {
        char* target_row = target_ptrs[i % row_count];
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        *(volatile char*)target_row;
        end = m5_rpns();
        // if (end > attack_period) 
        //      break;
        // end = m5_rpns();
        uint32_t access_latency = end - start;
        uint32_t time_to_next_access = distribution(generator);
        uint32_t time_to_sleep = access_latency < time_to_next_access ? time_to_next_access - access_latency : 0;
        fine_grained_sleep(time_to_sleep);
        start = m5_rpns();
    }
    std::cout << "[MRNOISE] I'm out at "<< end << std::endl;

    return 0;
}
