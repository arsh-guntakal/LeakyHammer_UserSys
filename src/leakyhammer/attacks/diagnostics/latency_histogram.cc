// Diagnostic receiver: what does a probing process see while a sender runs?
//
// It decodes nothing. For each transmission window it probes memory
// continuously and prints a histogram of the access latencies it observed,
// together with the bit the sender was sending (derived from the data pattern,
// which the sender and this program share). Comparing the histograms of "1" and
// "0" windows shows whether the sender's activity is visible at all, whatever
// decoder is used afterwards.
//
// Usage: <txn_period> <msg_bytes> <data_pattern> <rows> <first_row> <bank_group>
//        <bank> <sync_ns>
//   Probes <rows> distinct rows round-robin, starting at <first_row>, in the
//   given bank of rank 1, starting its first window at <sync_ns> like the
//   sender it is paired with. If mapping the rows takes longer than that, the
//   program says so: its windows are then misaligned with the sender's.

#define __STDC_FORMAT_MACROS

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>

#include <iostream>
#include <vector>

#include "rowhammer-addr.hh"
#include "rowhammer-side.hh"

// Upper edges of the latency bins in ns; the last bin is everything above.
static const uint64_t EDGES_NS[] = {100, 150, 200, 250, 300, 550,
                                    1000, 2000, 3000};
static const int NUM_EDGES = sizeof(EDGES_NS) / sizeof(EDGES_NS[0]);

const int NUM_CHANNEL = 1;
const int NUM_RANKS = 2;
const int PROBE_RANK = 1;
const int alloc_size = 64;
DDR5_16Gb_x8 target;

int main(int argc, char *argv[]) {
    if (argc < 9) {
        std::cout << "Usage: " << argv[0]
                  << " <txn_period> <msg_bytes> <data_pattern> <rows> "
                     "<first_row> <bank_group> <bank> <sync_ns>" << std::endl;
        return 1;
    }
    uint32_t period = std::atoi(argv[1]);
    int msg_bytes = std::atoi(argv[2]);
    char data_pattern = std::strtol(argv[3], NULL, 16);
    int nrows = std::atoi(argv[4]);
    int first_row = std::atoi(argv[5]);
    int bank_group = std::atoi(argv[6]);
    int bank = std::atoi(argv[7]);
    uint64_t sync_ns = std::strtoull(argv[8], NULL, 10);
    uint32_t timeout = period - 8000;

    target = DDR5_16Gb_x8(NUM_CHANNEL, NUM_RANKS, 0, PROBE_RANK, bank_group,
                          bank, 0, 0);
    std::vector<char*> rows(nrows, 0);
    for (int i = 0; i < nrows; i++) {
        target.row = first_row + i;
        rows[i] = (char*) mmap_atk(alloc_size, target.to_physical());
        assert(rows[i] != MAP_FAILED);
    }

    std::printf("[HIST] edges_ns:");
    for (int b = 0; b < NUM_EDGES; b++) std::printf(" %lu", EDGES_NS[b]);
    std::printf("\n"); FLUSH();

    if (m5_rpns() > sync_ns) {
        std::printf("[HIST] LATE: mapping the rows finished %lu ns after the "
                    "sync point\n", m5_rpns() - sync_ns); FLUSH();
    }
    sleep_until(sync_ns);
    uint64_t next_window = m5_rpns() + period;
    for (int w = 0; w < msg_bytes * 8; w++) {
        int bit = (data_pattern >> (7 - (w % 8))) & 1;
        std::vector<int> hist(NUM_EDGES + 1, 0);
        uint64_t start = m5_rpns();
        size_t idx = 0;
        while (m5_rpns() - start < timeout) {
            char* probe = rows[idx];
            idx = (idx + 1) % rows.size();
            asm volatile("clflush (%0)" : : "r"(probe) : "memory");
            uint64_t t1 = m5_rpns();
            *(volatile char*)probe;
            uint64_t latency = m5_rpns() - t1;
            int b = 0;
            while (b < NUM_EDGES && latency >= EDGES_NS[b]) b++;
            hist[b]++;
        }
        std::printf("[HIST] W %d sent %d :", w, bit);
        for (int count : hist) std::printf(" %d", count);
        std::printf("\n"); FLUSH();
        next_window += period;
        sleep_until(next_window);
    }
    std::printf("[HIST] DONE\n"); FLUSH();
    return 0;
}
