// =============================================================================
// TPRAC: Timing-Based RFMs for PRAC
// =============================================================================
//
// Woo, Qu, Saileshwar and Nair, "When Mitigations Backfire: Timing Channel
// Attacks and Defense for PRAC-Based RowHammer Mitigations", ISCA '25.
// Ported from the authors' "TimingBasedRFM" plugin
// (github.com/STAR-Laboratory/PRAC_TC_ISCA25), without its optional
// targeted-refresh path, which their TPRAC configurations leave disabled.
//
// PRAC's timing channel exists because the attacker decides when the
// mitigation (an Alert Back-Off) happens. TPRAC instead issues one RFMab per
// rank every TB-RFM window, whatever the activations are. Each RFM mitigates
// the most-activated row of every bank, which keeps counters below the ABO
// threshold, so the attacker-triggered back-off never fires and the only
// mitigation latency the receiver sees is periodic and data-independent.
//
// This plugin only schedules the RFMs. It must be listed together with the
// PRAC plugin (see tprac.yaml), which keeps the per-row counters, resets the
// top row of each bank on every RFMab it sees, and still raises an ABO if a
// counter reaches the threshold anyway (for example, with too long a window).
//
// PARAMETERS (see tprac.yaml)
//   tb_rfm_window_ns  Time between timing-based RFMs. The paper's default is
//                     one per tREFI (3900 ns). It must exceed tRFM (~295 ns).
// =============================================================================

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"

#include <cstdio>
#include <cstdlib>
#include <vector>

namespace Ramulator {

class TPRAC : public IControllerPlugin, public Implementation {
    RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, TPRAC, "TPRAC", "Timing-based RFMs for PRAC.")

private:
    IDRAM* m_dram = nullptr;

    Clk_t m_clk = 0;
    Clk_t m_window_clk = 0;
    Clk_t m_next_rfm_clk = 0;

    int m_rfm_req_id = -1;
    int m_num_levels = -1;
    int m_num_ranks = -1;

    int m_window_ns = -1;
    bool m_debug = false;

    uint64_t s_num_tb_rfm = 0;

public:
    void init() override {
        m_window_ns = param<int>("tb_rfm_window_ns").default_val(3900);
        m_debug = param<bool>("debug").default_val(false);
    }

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
        m_ctrl = cast_parent<IDRAMController>();
        m_dram = m_ctrl->m_dram;

        if (!m_dram->m_requests.contains("rfm")) {
            std::printf("[TPRAC] [CRITICAL ERROR] DRAM device does not support request: rfm\n");
            std::exit(1);
        }
        m_rfm_req_id = m_dram->m_requests("rfm");
        m_num_levels = m_dram->m_levels.size();
        m_num_ranks = m_dram->get_level_size("rank");

        m_window_clk = m_window_ns / ((float) m_dram->m_timing_vals("tCK_ps") / 1000.0f);
        // The first RFM is placed so that it completes at the end of the
        // first window, as in the authors' plugin.
        m_next_rfm_clk = m_window_clk - m_dram->m_timing_vals("nRFM1");
        if (m_next_rfm_clk <= 0) {
            std::printf("[TPRAC] [CRITICAL ERROR] tb_rfm_window_ns=%d is shorter than tRFM.\n", m_window_ns);
            std::exit(1);
        }

        register_stat(s_num_tb_rfm).name("tprac_num_tb_rfm");

        if (m_debug) {
            std::printf("[TPRAC] window: %d ns = %ld clk, first RFM at clk %ld\n",
                m_window_ns, m_window_clk, m_next_rfm_clk);
        }
    }

    void update(bool request_found, ReqBuffer::iterator& req_it) override {
        m_clk++;
        if (m_clk != m_next_rfm_clk) {
            return;
        }
        for (int rank = 0; rank < m_num_ranks; rank++) {
            std::vector<int> addr_vec(m_num_levels, -1);
            addr_vec[0] = m_ctrl->m_channel_id;
            addr_vec[1] = rank;
            Request rfm(addr_vec, m_rfm_req_id);
            if (!m_ctrl->priority_send(rfm)) {
                std::printf("[TPRAC] [CRITICAL ERROR] Could not enqueue RFMab for rank %d at clk %ld.\n", rank, m_clk);
                std::exit(1);
            }
            s_num_tb_rfm++;
            if (m_debug) {
                std::printf("[TPRAC] [%ld] RFMab rank %d\n", m_clk, rank);
            }
        }
        m_next_rfm_clk += m_window_clk;
    }
};

}       // namespace Ramulator
