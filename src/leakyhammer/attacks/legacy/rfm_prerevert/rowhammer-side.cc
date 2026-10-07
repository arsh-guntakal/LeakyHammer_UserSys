#include "rowhammer-side.hh"
#include <iostream>

// #define VERBOSE

long mmap_atk(size_t mem_size, long paddr) {
    return syscall(SYS_MMAP_ATK, NULL, paddr, mem_size, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, 0);
}

uint32_t fine_grained_sleep(uint32_t sleep_ns) {
    uint32_t magic_cap = (uint32_t) sleep_ns * 0.74f;
    volatile int x = 0;
    while (magic_cap-- > 0) {
        x++;
    }
    return x;
}

void sleep_until(uint64_t target) {
    while(m5_rpns() < target);
}

void sidech_stream(std::vector<char*>& target_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    while(m5_rpns() - start < timeout) {
        for(char* cur_ptr: target_ptrs) {
            asm volatile("clflush (%0)" : : "r" (cur_ptr) : "memory");
        }
        for(char* cur_ptr: target_ptrs) {
            *(volatile char*)cur_ptr;
            if(m5_rpns() - start >= timeout) return;
        }
    }
}

void prac_synchronize(std::vector<char*>& row_ptrs, int low_thresh, int high_thresh, int consecutive_passes) {
    #ifdef VERBOSE
        std::printf("[SYNC] Break Thresh: (%d, %d)\n", low_thresh, high_thresh); FLUSH();
    #endif
    int sample_acts = 0;
    int cur_passes = 0;
    uint64_t total_latency = 0;
    int num_accesses = 0;
    while(true) {
        uint64_t max_latency = 0;
        for(char* ptr: row_ptrs) {
            bool row_hit = true;
            while(row_hit) {
                asm volatile("clflush (%0)" : : "r" (ptr) : "memory");
                asm volatile("mfence");
                uint64_t ns1 = m5_rpns();
                *(volatile char*)ptr;
                uint64_t ns2  = m5_rpns();
                uint64_t cur_latency = ns2 - ns1;
                total_latency += ns2 - ns1;
                num_accesses++;
                max_latency = std::max<uint64_t>(max_latency, cur_latency);
                uint64_t hit_cap = (int) (total_latency / num_accesses) * 0.6f;
                row_hit = cur_latency < hit_cap;
            }
            fine_grained_sleep(300);
        }
        sample_acts++;
        if (max_latency > PERIODIC_CAP_NS) {
            #ifdef VERBOSE
                std::printf("[SYNC] Back-Off observed at %d ACTs\n", sample_acts); FLUSH();
            #endif
            bool pass_low = sample_acts > low_thresh;
            bool pass_high = sample_acts < high_thresh;
            bool pass_success = pass_low && pass_high;
            cur_passes = pass_success ? cur_passes + 1 : 0;
            uint64_t avg_latency = total_latency / num_accesses;
            int avg_thresh = (high_thresh + low_thresh) / 2;
            if (pass_success) {
                fine_grained_sleep(avg_latency * avg_thresh * 2);
            }
            sample_acts = 0;
            #ifdef VERBOSE
                std::printf("[SYNC] Current Passes: %d\n", cur_passes); FLUSH();
            #endif
            if (cur_passes >= consecutive_passes) {
                break;
            }
        }
    }
}

void prac_send(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > PERIODIC_CAP_NS) {
            return;
        }
    }
}

bool prac_receive(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    int num_acts = 0;
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        num_acts++;
        if (latency > PERIODIC_CAP_NS) {
            // std::cout << "[RECV] Latency: " << latency << std::endl; FLUSH();
            // std::printf("[RECV] Num ACTs: %d\n", num_acts); FLUSH();
            return true;
        }
    }
    return false;
}

void prac_wait_stream(std::vector<char*>& col_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    int access_idx = 0;
    while(m5_rpns() - start < timeout) {
        char* cur_ptr = col_ptrs[access_idx++ % col_ptrs.size()];
        asm volatile("clflush (%0)" : : "r" (cur_ptr) : "memory");
        *(volatile char*)cur_ptr;
    }
}

void pracrand_synchronize(std::vector<char*>& row_ptrs, bool is_sender) {
    char* sync_row = row_ptrs[is_sender ? 0 : 1];
    while(true) {
        asm volatile("clflush (%0)" : : "r" (sync_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)sync_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > PERIODIC_CAP_NS) {
            return;
        }
    }
}

void pracrand_send(std::vector<char*>& row_ptrs, uint32_t send_duration, bool bit) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[bit ? 0 : 1];
    while(m5_rpns() - start < send_duration) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        *(volatile char*)target_row;
    }
}

bool pracrand_receive(char* recv_row, uint32_t recv_duration, int assert_thresh) {
    uint64_t start = m5_rpns();
    int num_backoffs = 0;
    while(m5_rpns() - start < recv_duration) {
        asm volatile("clflush (%0)" : : "r" (recv_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)recv_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > PERIODIC_CAP_NS) {
            num_backoffs++;
        }
    }
    return num_backoffs > assert_thresh;
}

void trigger_rfm(std::vector<char*>& row_ptrs, int rfm_th) { }

bool wait_rfm(char* row_ptr) {
    while(true) {
        asm volatile("clflush (%0)" : : "r" (row_ptr) : "memory");
        asm volatile("mfence");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)row_ptr;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > PERIODIC_CAP_NS) {
            // Delayed periodic refreshes
            return false;
        }
        else if (latency > ACCESS_CAP_NS) {
            // RFM
            return true;
        }
    }
}

bool wait_rfm_stream(std::vector<char*>& col_ptrs) {
    int access_idx = 0;
    while(true) {
        char* cur_ptr = col_ptrs[access_idx++ % col_ptrs.size()];
        asm volatile("clflush (%0)" : : "r" (cur_ptr) : "memory");
        asm volatile("mfence");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)cur_ptr;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > PERIODIC_CAP_NS) {
            // Delayed periodic refreshes
            return false;
        }
        else if (latency > ACCESS_CAP_NS) {
            // RFM
            return true;
        }
    }
}

void rfm_synchronize(std::vector<char*>& row_ptrs, bool is_sender) {
    // TODO: implement robust algorithm
    // ALG: Consecutive ACK loop
    // Attacker triggers, Receiver observes and roles switch
    // Observations have timeout, round fails on timeout (i.e., both start waiting for RFM)
    char* shared_row = row_ptrs[is_sender ? 1 : 0];
    while (wait_rfm(shared_row));
}

bool rfm_receive(std::vector<char*>& row_ptrs, int assert_thresh, uint32_t timeout) {
    int rfm_ctr = 0;
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > ACCESS_CAP_NS && latency < PERIODIC_CAP_NS_RFM) {
            rfm_ctr++;
        }
    }
    // std::printf("[RECV] Received: %d (%d RFMs)\n", rfm_ctr > assert_thresh, rfm_ctr); FLUSH();
    return rfm_ctr > assert_thresh;
}

bool rfm_receive_poc(std::vector<char*>& row_ptrs, int assert_thresh, uint32_t timeout) {
    int rfm_ctr = 0;
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > ACCESS_CAP_NS && latency < PERIODIC_CAP_NS_RFM) {
            rfm_ctr++;
        }
    }
    std::printf("[RECV] Received: %d (%d RFMs)\n", rfm_ctr > assert_thresh, rfm_ctr); FLUSH();
    return rfm_ctr > assert_thresh;
}

void rfm_send(std::vector<char*>& row_ptrs) {
    uint64_t latency = 0;
    int access_ctr = 0;
    while(latency < PERIODIC_CAP_NS) {
        char* ptr = row_ptrs[access_ctr++ % row_ptrs.size()];
        asm volatile("clflush (%0)" : : "r" (ptr) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)ptr;
        uint64_t ns2 = m5_rpns();
        latency = ns2 - ns1;
    }
}

bool receive_nosync(std::vector<char*>& row_ptrs, int assert_cap, int window) {
    std::vector<int> samples;
    uint64_t start = m5_rpns();
    uint64_t end = start + window;
    while(true) {
        int sampled_acts = 0;
        while(true) {
            uint64_t latency = 0;
            for(char* ptr: row_ptrs) {
                asm volatile("clflush (%0)" : : "r" (ptr) : "memory");
                uint64_t ns1 = m5_rpns();
                *(volatile char*)ptr;
                uint64_t ns2  = m5_rpns(); 
                latency = std::max<uint64_t>(latency, ns2 - ns1);
            }
            sampled_acts++;
            if (latency > PERIODIC_CAP_NS) {
                std::printf("[RECV] ACTs: %d Latency: %ld\n", sampled_acts, latency);
                samples.push_back(sampled_acts);
                break;
            }
        }
    uint64_t now = m5_rpns();
    if (now >= end)
        break;
    }
    // check how many samples are below the assert cap
    int num_below = 0;
    for(int sample: samples) {
        if (sample < assert_cap) {
            num_below++;
        }
    }
    return num_below >= (int) samples.size() / 2;
}

void send_nosync(std::vector<char*>& row_ptrs, int setup_acts, int window) {
    uint64_t start = m5_rpns();
    uint64_t end = start + window;
    while(true) {
        for(int i = 0; i < setup_acts; i++) {
            for(char* ptr: row_ptrs) {
                asm volatile("clflush (%0)" : : "r" (ptr) : "memory");
                *(volatile char*)ptr;
            }
        }
        uint64_t now = m5_rpns();
        if (now >= end)
            break;
    }
}


void drama_send(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        *(volatile char*)target_row;
    }
}

bool drama_receive(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    int num_acts = 0;
    int sum_latency = 0;
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > DRAMA_UPPERLIMIT_NS)
            continue;
        num_acts++;
        sum_latency += latency;
        //std::printf("[RECV] Latency: %ld\n", latency); FLUSH();
    }
    if (num_acts == 0)
        return true;
    return ((sum_latency/num_acts) > DRAMA_CAP_NS);
}

void drama_wait_stream(std::vector<char*>& col_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    // int access_idx = 0;
    while(m5_rpns() - start < timeout) {
        // char* cur_ptr = col_ptrs[access_idx++ % col_ptrs.size()];
        // asm volatile("clflush (%0)" : : "r" (cur_ptr) : "memory");
        // *(volatile char*)cur_ptr;
    }
}


void multi_sender(std::vector<char*>& row_ptrs, std::vector<char*>& col_ptrs, int msg, uint32_t timeout) {
    //std::printf("[SEND] Message: %d\n", msg); FLUSH();
    uint32_t time_step = timeout / 4;
    if (msg == 0) {
        prac_wait_stream_multi(col_ptrs, timeout);
    }
    else if (msg == 1) {
        bool cont_flag = prac_wait_stream_multi(col_ptrs, time_step*2);
        if (cont_flag)
            prac_multi_send(row_ptrs, time_step);
    }
    else if (msg == 2) {
        bool cont_flag = prac_wait_stream_multi(col_ptrs, time_step*0.5);
        if (cont_flag)
            prac_multi_send(row_ptrs, time_step*2);
    }
    else {
        prac_multi_send(row_ptrs, timeout);
    }
}

void prac_multi_send(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    int num_act = 0;
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        num_act++;
        if (latency > PERIODIC_CAP_NS) {
            std::printf("[SEND] Num ACTs - 1: %d\n", num_act); FLUSH();
            return;
        }
    }
    std::printf("[SEND] Num ACTs - 1: %d\n", num_act); FLUSH();
    return;
}

int prac_multi_receive(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    //while(m5_rpns() - start < timeout/4) {}
    //std::printf("[RECV] STARTING\n"); FLUSH();
    char* target_row = row_ptrs[0];
    int num_acts = 0;
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        num_acts++;
        if (latency > PERIODIC_CAP_NS) {
            break;
        }
    }
    std::printf("[RECV] Num ACTs: %d\n", num_acts); FLUSH();
    if (num_acts < MULTI_CAP_10) return 3;
    else if (num_acts < MULTI_CAP_01) return 2;
    else if (num_acts < MULTI_CAP_00) return 1;
    else return 0;
}

bool prac_wait_stream_multi(std::vector<char*>& col_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    int access_idx = 0;
    int num_acts = 0;
    while(m5_rpns() - start < timeout) {
        char* cur_ptr = col_ptrs[access_idx++ % col_ptrs.size()];
        asm volatile("clflush (%0)" : : "r" (cur_ptr) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)cur_ptr;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        num_acts++;
        if (latency > PERIODIC_CAP_NS) {
            return false;
        }
    }
    std::printf("[SEND] Num ACTs - 0: %d\n", num_acts); FLUSH();
    return true;
}


void ternary_sender(std::vector<char*>& row_ptrs, std::vector<char*>& col_ptrs, int msg, uint32_t timeout) {
    //std::printf("[SEND] Message: %d\n", msg); FLUSH();
    uint32_t time_step = timeout / 3;
    if (msg == 0) {
        prac_wait_stream_multi(col_ptrs, timeout);
    }
    else if (msg == 1) {
        bool cont_flag = prac_wait_stream_multi(col_ptrs, time_step*1.75);
        if (cont_flag)
            prac_multi_send(row_ptrs, time_step);
    }
    else if (msg == 2) {
        prac_multi_send(row_ptrs, timeout);
    }
}

int ternary_receive(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    //while(m5_rpns() - start < timeout/4) {}
    //std::printf("[RECV] STARTING\n"); FLUSH();
    char* target_row = row_ptrs[0];
    int num_acts = 0;
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        num_acts++;
        if (latency > PERIODIC_CAP_NS) {
            break;
        }
    }
    std::printf("[RECV] Num ACTs: %d\n", num_acts); FLUSH();
    if (num_acts > TERNARY_CAP_UP) return 0;
    else if (num_acts > TERNARY_CAP_DOWN) return 1;
    else return 2;
}



void prac_latency_send(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > PERIODIC_CAP_NS) {
            return;
        }
    }
}

bool prac_latency_receive(std::vector<char*>& row_ptrs, uint32_t timeout, uint64_t threshold, uint64_t delayed_ref) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    int num_acts = 0;
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        //std::cout << "[RECV] Latency: " << latency << std::endl; FLUSH();
        num_acts++;
        if ((latency > threshold) && (latency < delayed_ref)) {
            std::cout << "[RECV] potential back-off: " << latency << std::endl; FLUSH();
            //std::printf("[RECV] Num ACTs: %d\n", num_acts); FLUSH();
            return true;
        }
    }
    return false;
}

bool prac_trefi_send(std::vector<char*>& row_ptrs, uint32_t timeout, uint32_t max_lat) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    uint64_t last_high_lat_clk = 0;
    // std::printf("[SEND] Sending until %lu\n", start + timeout);
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        bool high_lat = latency > ACCESS_CAP_NS;
        if (!high_lat) {
            continue;
        }
        uint64_t high_lat_diff = m5_rpns() - last_high_lat_clk;
        // std::printf("[SEND] @%lu High latency %lu (Diff: %lu)\n", m5_rpns(), latency, high_lat_diff);
        if (high_lat_diff < max_lat) {
            return true;
        }
        last_high_lat_clk = m5_rpns();
    }
    return false;
}

// DREAM-C: hammer target rows until DRFMab fires (latency spike), then return.
// The DREAM-C plugin fires DRFMab after `threshold` activations to any rows sharing
// the same DCT group (group_id = row_id / gang_size). With threshold=40 and gang_size=32,
// rows 0 and 1 both land in group 0, so 40 hammers to either row triggers DRFMab.
//
// We MUST alternate between at least two distinct rows in the same gang. Hammering
// a single row is a row-buffer hit on every access (no ACT, no counter increment)
// when the controller's RowPolicy keeps the row open. Alternating rows forces an
// activate on every iteration, so the DREAM counter actually accumulates.
void dream_send(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    size_t n_rows = row_ptrs.size();
    size_t idx = 0;
    while (m5_rpns() - start < timeout) {
        char* target_row = row_ptrs[idx];
        idx++;
        if (idx >= n_rows) idx = 0;
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        // DRFMab stalls all banks; latch is in the range above normal row miss but below PRAC ABO
        if (latency > DREAM_DRFMAB_CAP_NS && latency < PERIODIC_CAP_NS) {
            return;
        }
    }
}

// DREAM-C: count DRFMab stalls observed on the receiver's bank during the window.
// Because DRFMab stalls ALL banks in the sub-channel, the receiver on any bank will
// see the same latency spike when the sender triggers DRFMab. Returns true if at
// least DREAM_ASSERT_THRESH spikes are observed (i.e., sender was hammering).
bool dream_receive(std::vector<char*>& row_ptrs, uint32_t timeout) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    int drfm_ctr = 0;
    while (m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > DREAM_DRFMAB_CAP_NS && latency < PERIODIC_CAP_NS) {
            drfm_ctr++;
        }
    }
    return drfm_ctr > DREAM_ASSERT_THRESH;
}

// DREAM-C v2: spread-row, rate-throttled receiver. Round-robins probes across
// N rows that each map to a distinct DCT gang (group_id = row_id / gang_size).
//
// Two design constraints:
//   1. Per-gang ACT rate must stay below DREAM's threshold (40 / 64ms / gang)
//      or the receiver triggers DRFMab on its own bank, indistinguishable from
//      the sender. Round-robin across N gangs divides the receiver's per-gang
//      ACT rate by N.
//   2. Probe interval must be <= DRFMab stall duration (~7us) so every stall
//      gets caught by at least one probe.
//
// We satisfy both by enforcing a probe_interval_ns spacing between probes.
// With N=512 gangs and probe_interval=5us:
//   - probes per attack: 16ms / 5us = 3200; per-gang ACTs: 6.25 (< 10 budget)
//   - probes per 20us window: 4; each probe spans 5us so catches any 7us stall
int dream_receive_count(std::vector<char*>& row_ptrs, uint32_t timeout,
                        uint32_t probe_interval_ns) {
    uint64_t start = m5_rpns();
    int drfm_ctr = 0;
    size_t n_rows = row_ptrs.size();
    size_t idx = 0;
    uint64_t next_probe = start;
    while (m5_rpns() - start < timeout) {
        // Throttle: wait until next scheduled probe time. Skip throttle if
        // probe_interval_ns is 0 (full speed mode for back-compat).
        if (probe_interval_ns > 0) {
            while (m5_rpns() < next_probe) { /* spin */ }
            next_probe += probe_interval_ns;
        }
        char* target_row = row_ptrs[idx];
        idx++;
        if (idx >= n_rows) idx = 0;
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2 = m5_rpns();
        uint64_t latency = ns2 - ns1;
        if (latency > DREAM_DRFMAB_CAP_NS && latency < PERIODIC_CAP_NS) {
            drfm_ctr++;
        }
    }
    return drfm_ctr;
}

bool prac_trefi_receive(std::vector<char*>& row_ptrs, uint32_t timeout, uint32_t max_lat) {
    uint64_t start = m5_rpns();
    char* target_row = row_ptrs[0];
    uint64_t last_high_lat_clk = 0;
    // std::printf("[RECV] Listening until %lu\n", start + timeout);
    while(m5_rpns() - start < timeout) {
        asm volatile("clflush (%0)" : : "r" (target_row) : "memory");
        uint64_t ns1 = m5_rpns();
        *(volatile char*)target_row;
        uint64_t ns2  = m5_rpns();
        uint64_t latency = ns2 - ns1;
        bool high_lat = latency > ACCESS_CAP_NS;
        if (!high_lat) {
            continue;
        }
        uint64_t high_lat_diff = m5_rpns() - last_high_lat_clk;
        // std::printf("[RECV] @%lu High latency: %lu (Diff: %lu)\n", m5_rpns(), latency, high_lat_diff);
        if (high_lat_diff < max_lat) {
            return true;
        }
        last_high_lat_clk = m5_rpns();
    }
    return false;
}