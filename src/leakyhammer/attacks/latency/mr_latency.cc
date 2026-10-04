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

#define NUM_COLUMNS     64

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
DDR5_16Gb_x8 target;
const int alloc_size = 64;

int stream = 0;
int incr = 64;

int main(int argc, char *argv[]) {
    if (argc < 3) {
        std::cout << "Usage: " << argv[0] << " <iterations> <row_count> [col_accesses]" << std::endl;
        return 1;
    }

    int iterations = std::atoi(argv[1]);
    int row_count = std::atoi(argv[2]);

    // N_CH, N_RA, CH, RA, BG, BA, RO, CO
    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, 1, 7, 3, 0, 31);

    std::vector<char*> target_ptrs(row_count, 0);

    for (int i = 0; i < row_count; i++) {
        target.row = i;
        target_ptrs[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(target_ptrs[i] != MAP_FAILED);
    }

    std::vector<uint32_t> latencies(iterations, 0);

    for (int i = 0; i < row_count; i++) {
        target.row = i;
        *(volatile char*)target_ptrs[i];
    }

    std::printf("Accesses Begin\n"); FLUSH();
    uint64_t start = m5_rpns();
    for (int i = 0; i < iterations; i++) {
        char* target_row = target_ptrs[i % row_count];
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        *(volatile char*)target_row;
        uint64_t end = m5_rpns();
        latencies[i] = end - start;
        start = end;
    }

    std::printf("Dump Begin\n"); FLUSH();
    for (int i = 0; i < iterations; i++) {
        std::printf("%d: Latency: %d\n", i, latencies[i]);
    }

    
    return 0;
}