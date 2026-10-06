#ifndef ROWHAMMER_SIDECH_H_
#define ROWHAMMER_SIDECH_H_

#include <vector>
#include <cstdint>
#include <cstddef>
#include <limits>

#include <gem5/m5ops.h>
#include <sys/mman.h>
#include <unistd.h>

#define FLUSH()                 fflush(stdout)
#define SYS_MMAP_ATK            451
#define PERIODIC_CAP_NS         8000
#define PERIODIC_CAP_NS_RFM     6000
#define ACCESS_CAP_NS           2000
#define SYNC_ITERS              4
#define TREFI                   3900

#define PRAC_TXN_PERIOD         32000
#define PRAC_BACKOFF_THRESH     128
#define PRAC_TIMEOUT            (PRAC_TXN_PERIOD - 6000)

#define PRACRAND_TXN_DURATION   140000
#define PRACRAND_TXN_PERIOD     (PRACRAND_TXN_DURATION + 8000)
#define PRACRAND_ASSERT_THRESH  6

#define COLUMN_CAP              16

#define SYNC_POINT              220000

#define DRAMA_CAP_NS            60
#define DRAMA_UPPERLIMIT_NS     150

#define MULTI_CAP_00             240 // 335 // 300
#define MULTI_CAP_01             180 // 275 // 250 // 225
#define MULTI_CAP_10             130 // 130 // 130

#define TERNARY_CAP_UP        240
#define TERNARY_CAP_DOWN      130

// DREAM-C DRFMab detection
// DRFMab (nDRFMab=5000 mem cycles) is expected to be CPU-visible at ~2000-7000ns
// based on the same ~7-20x amplification factor observed for RFM
#define DREAM_DRFMAB_CAP_NS   2000    // Lower bound: well above normal row miss (~500ns)
#define DREAM_DRFMAB_UPPER_NS 7500    // Upper bound: below PRAC ABO (8000ns)
#define DREAM_ASSERT_THRESH   0       // Sender produces ~1 DRFMab per "1" window; require >0 spikes (i.e. >=1) to decode "1"
#define DREAM_TXN_PERIOD      50000   // Window size (ns); 40 hammers ~20us => 2+ DRFMab per window

long mmap_atk(size_t mem_size, long paddr);
uint32_t fine_grained_sleep(uint32_t sleep_ns);
void sleep_until(uint64_t target);
void sidech_stream(std::vector<char*>& target_ptrs, uint32_t timeout);

void prac_synchronize(std::vector<char*>& row_ptrs, int low_thresh, int high_thresh, int consecutive_passes);
void prac_send(std::vector<char*>& row_ptrs, uint32_t timeout);
bool prac_receive(std::vector<char*>& row_ptrs, uint32_t timeout);

void pracrand_synchronize(std::vector<char*>& row_ptrs, bool is_sender);
void pracrand_send(std::vector<char*>& row_ptrs, uint32_t send_duration, bool bit);
bool pracrand_receive(char* recv_row, uint32_t recv_duration, int assert_thresh);

void drama_send(std::vector<char*>& row_ptrs, uint32_t timeout);
bool drama_receive(std::vector<char*>& row_ptrs, uint32_t timeout);
void drama_wait_stream(std::vector<char*>& col_ptrs, uint32_t timeout);

void multi_sender(std::vector<char*>& row_ptrs, std::vector<char*>& col_ptrs, int msg, uint32_t timeout);
void prac_multi_send(std::vector<char*>& row_ptrs, uint32_t timeout);
int prac_multi_receive(std::vector<char*>& row_ptrs, uint32_t timeout);
bool prac_wait_stream_multi(std::vector<char*>& col_ptrs, uint32_t timeout);
void ternary_sender(std::vector<char*>& row_ptrs, std::vector<char*>& col_ptrs, int msg, uint32_t timeout);
int ternary_receive(std::vector<char*>& row_ptrs, uint32_t timeout);

void prac_latency_send(std::vector<char*>& row_ptrs, uint32_t timeout);
bool prac_latency_receive(std::vector<char*>& row_ptrs, uint32_t timeout,uint64_t threshold, uint64_t delayed_ref);

bool wait_rfm(char* row_ptr);
bool wait_rfm_stream(std::vector<char*>& col_ptrs);
void rfm_synchronize(std::vector<char*>& row_ptrs, bool is_sender);
void rfm_send(std::vector<char*>& row_ptrs);
bool rfm_receive(std::vector<char*>& row_ptrs, int assert_thresh, uint32_t timeout);
bool rfm_receive_poc(std::vector<char*>& row_ptrs, int assert_thresh, uint32_t timeout);
int rfm_receive_rfmctr(std::vector<char*>& row_ptrs, int assert_thresh);

bool prac_trefi_send(std::vector<char*>& row_ptrs, uint32_t timeout, uint32_t max_lat);
bool prac_trefi_receive(std::vector<char*>& row_ptrs, uint32_t timeout, uint32_t max_lat);

// DREAM-C: detect DRFMab events (all-bank stall triggered by row-group activation counter)
void dream_send(std::vector<char*>& row_ptrs, uint32_t timeout);
bool dream_receive(std::vector<char*>& row_ptrs, uint32_t timeout);
// v2: round-robin probes across N rows in N distinct gangs with rate-throttled
// probing (probe_interval_ns spacing). Returns raw spike count for rate-based decoding.
int  dream_receive_count(std::vector<char*>& row_ptrs, uint32_t timeout,
                         uint32_t probe_interval_ns);

#endif  // ROWHAMMER_SIDECH_H_
