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
// Latency-band constants used by all PRAC/RFM receivers to classify a probe
// access by its observed CPU-visible latency.
//   - latency > ACCESS_CAP_NS         -> above a normal row-miss
//   - latency > PERIODIC_CAP_NS_RFM   -> looks like a back-off (PRAC) rather than RFM
//   - latency > PERIODIC_CAP_NS       -> definitely a back-off / long stall
// These values were the artifact's defaults and produce a working RFM POC
// (see figures/figure6bak.pdf). They were briefly inflated to 2000/6000/8000
// in commit e462c3e ("[broken] added support for DREAM ...") to accommodate a
// matching nDRFMab=5000 mem-cycle inflation in DDR5-VRR.cpp; that change broke
// the RFM POC and has been reverted alongside the simulator revert.
#define PERIODIC_CAP_NS         1300 // 1000
#define PERIODIC_CAP_NS_RFM     550
#define ACCESS_CAP_NS           250
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

// DREAM-C DRFMab detection.
//
// Post-revert (DDR5-VRR.cpp at JEDEC formulas) DRFMab uses
//   nDRFMab = 2 * BRC * tRRFsb_TABLE[0][density_id]   (~140 ns at the DRAM)
// which is the same family of values that drive nRFM* — empirically the RFM
// POC sees those stalls in the (250, 550) ns CPU-visible band, so DRFMab
// stalls should land in roughly the same place. Start from the RFM band
// and tune from the receiver's spike-count histogram.
//
// Pre-revert (commit e462c3e era), nDRFMab was overridden to 5000 mem cycles
// (~3 us at the DRAM, ~2-7 us CPU-visible) and these constants were
// 2000 / 7500. Don't be tempted to "go back" to those values — DRFMab now
// lives where RFM does.
#define DREAM_DRFMAB_CAP_NS   250     // Lower bound: above a normal row miss
#define DREAM_DRFMAB_UPPER_NS 1300    // Upper bound: below a PRAC back-off / periodic stall
#define DREAM_ASSERT_THRESH   0       // (legacy boolean receiver — unused; v2 uses DREAM_DECODE_THRESH)
#define DREAM_TXN_PERIOD      50000   // Window size (ns); only consulted as a default — actual matrix value is in run_config.py

// RRS todo
#define RRS_SWAP_CAP_NS 3000
#define RRS_PERIODIC_CAP_NS 500000
#define RRS_ASSERT_THRESH 1

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

// DREAM-C: detect DRFMab events (all-bank stall triggered by row-group
// activation counter).
//
// All these helpers assume the Ramulator2 DREAM plugin is configured with
// `grouping: random` (the paper-default). Under that grouping the plugin
// hashes each ACT to a DCT entry as
//
//     idx = (row XOR mask[rank][bank_in_rank]) mod num_dct_entries
//
// where `mask[r][b]` is generated deterministically from the YAML `seed`
// at simulator init. Because XOR-with-mask is a bijection (and num_entries
// equals num_rows_per_bank when vertical_sharing=1), TWO ROWS IN THE SAME
// BANK CANNOT SHARE A DCT ENTRY under random grouping. The sender therefore
// has to coordinate ACTs from TWO DIFFERENT BANKS at row addresses that
// XOR-through different masks to the same DCT index. The receiver must
// likewise know its bank's mask to pick rows that span N distinct DCT
// entries while avoiding the sender's entry.
//
// Use `dream_compute_random_masks` to replicate the plugin's mask table
// in userspace; keep its arguments in sync with `dream.yaml` (`seed`) and
// the DRAM organization (`num_ranks`, `num_banks_per_rank`,
// `num_dct_entries = num_rows_per_bank / vertical_sharing`).

// Replicates the Ramulator2 DREAM plugin's per-(rank, bank) XOR-mask table
// bit-for-bit. Returned shape: result[rank][bank_in_rank].
std::vector<std::vector<int>>
dream_compute_random_masks(uint64_t seed,
                           int num_ranks,
                           int num_banks_per_rank,
                           int num_dct_entries);

// `bank_in_rank` index used by the plugin: bank + bg * num_banks_per_group.
// Helper provided so callers don't have to hard-code the math.
int dream_bank_in_rank(int bg, int ba, int num_banks_per_group);

// Hammer all rows in `row_ptrs` round-robin for the full timeout window.
// Caller MUST construct `row_ptrs` so that every entry maps to the SAME
// DCT index under the plugin's random grouping (use the masks returned by
// `dream_compute_random_masks` to compute collision-targeted row IDs).
// Hammering rows that don't share a DCT entry will spread the per-counter
// ACT rate across multiple counters and starve the threshold trigger.
void dream_send_random_gang(std::vector<char*>& row_ptrs, uint32_t timeout);

// Round-robin probe over `row_ptrs`, with `probe_interval_ns` spacing
// between probes (set to 0 for full speed). Returns raw count of latency
// spikes in the DREAM detection band per window.
//
// Caller MUST construct `row_ptrs` so that every entry maps to a DISTINCT
// DCT index AND none of those indices collide with the sender's DCT entry
// (otherwise the receiver self-triggers DRFMab on its own bank,
// indistinguishable from the sender's events).
int dream_receive_count_random_gang(std::vector<char*>& row_ptrs,
                                    uint32_t timeout,
                                    uint32_t probe_interval_ns);


// RRS: 
void rrs_send(std::vector<char*>& row_ptrs, uint32_t timeout);
bool rrs_receive(std::vector<char*>& row_ptrs, uint32_t timeout);
bool rrs_receive_poc(std::vector<char*>& row_ptrs, uint32_t timeout);


#endif  // ROWHAMMER_SIDECH_H_
