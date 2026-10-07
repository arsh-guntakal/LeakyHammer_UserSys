#ifndef ROWHAMMER_ADDR_HH_
#define ROWHAMMER_ADDR_HH_

#include <cmath>
#include <map>

template <typename T>
T guard_mask(int begin, int length);

template <typename T>
T make_bits(int bits, int begin, int length);

class DRAMAddr {
public:
    using Addr_t = uint32_t;

    int num_channels;
    int num_ranks;
    int channel;
    int rank;
    int bankgroup;
    int bank;
    int row;
    int column;

    DRAMAddr() {
        update(1, 2, -1, -1, -1, -1, -1, -1);
    }

    DRAMAddr(int ch, int rk, int bg, int bk, int rw, int cl) {
        update(1, 2, -1, -1, -1, -1, -1, -1);
    }

    DRAMAddr(int n_ch, int n_rk, int ch, int rk, int bg, int b, int rw, int cl) {
        update(n_ch, n_rk, ch, rk, bg, b, rw, cl);
    }

    void update(int n_ch, int n_rk, int ch, int rk, int bg, int b, int rw, int cl) {
        num_channels = n_ch;
        num_ranks = n_rk;
        channel = ch;
        rank = rk;
        bankgroup = bg;
        bank = b;
        row = rw;
        column = cl;
    }

    virtual Addr_t to_physical() = 0;
};

class DDR5_16Gb_x8: public DRAMAddr {
public:
    using DRAMAddr::DRAMAddr;

    virtual Addr_t to_physical() override {
        return make_robaracoch(num_channels, num_ranks, channel, rank, bankgroup, bank, row, column);
    }

    static Addr_t make_robaracoch(int n_ch, int n_ra, int ch, int ra, int bg, int ba, int ro, int co) {
        int n_bg_bits = std::log2(N_BANKGROUPS);
        int n_bank_bits = std::log2(N_BANKS_PER_GRP);
        int n_row_bits = std::log2(N_ROWS);
        int n_col_bits = std::log2(N_COLS) - PREFETCH_BITS;
        int n_ch_bits = std::log2(n_ch);
        int n_rank_bits = std::log2(n_ra);

        // std::printf("CH: %d\n", n_ch_bits);
        // std::printf("CO: %d\n", n_col_bits);
        // std::printf("RA: %d\n", n_rank_bits);
        // std::printf("BA: %d\n", n_bank_bits);
        // std::printf("BG: %d\n", n_bg_bits);
        // std::printf("RO: %d\n", n_row_bits);
        // TODO: Order is hardcoded for RoBaRaCoCh @Oguzhan
        // (bc im lazy to make it generic and it never changes FOR NOW xd)
        int ch_off = TX_BITS;
        int col_off = ch_off + n_ch_bits;
        int rank_off = col_off + n_col_bits;
        int bank_off = rank_off + n_rank_bits;
        int bg_off = bank_off + n_bank_bits;
        int row_off = bg_off + n_bg_bits;

        Addr_t ch_bits = make_bits<Addr_t>(ch, ch_off, n_ch_bits);
        Addr_t col_bits = make_bits<Addr_t>(co, col_off, n_col_bits);
        Addr_t bank_bits = make_bits<Addr_t>(ba, bank_off, n_bank_bits);
        Addr_t bg_bits = make_bits<Addr_t>(bg, bg_off, n_bg_bits);
        Addr_t rank_bits = make_bits<Addr_t>(ra, rank_off, n_rank_bits);
        Addr_t row_bits = make_bits<Addr_t>(ro, row_off, n_row_bits);

        // std::printf("CH: %08x\n", ch_bits);
        // std::printf("CL: %08x\n", col_bits);
        // std::printf("BK: %08x\n", bank_bits);
        // std::printf("BG: %08x\n", bg_bits);
        // std::printf("RK: %08x\n", rank_bits);
        // std::printf("RW: %08x\n", row_bits);

        Addr_t addr = ch_bits | col_bits | bank_bits | bg_bits | rank_bits | row_bits;
        return addr;
    }

private:
    static const int N_BANKGROUPS = 8;
    static const int N_BANKS_PER_GRP = 4;
    static const int N_ROWS = 1 << 16;
    static const int N_COLS = 1 << 10;
    static const int TX_BITS = 6;
    static const int PREFETCH_SIZE = 16;
    static const int PREFETCH_BITS = std::log2(PREFETCH_SIZE);
};

template <typename T>
T guard_mask(int begin, int length) {
    uint64_t mask = ~((uint64_t) 0);
    mask <<= length;
    mask = ~mask << begin;
    return mask;
}

template <typename T>
T make_bits(int bits, int begin, int length) {
    T mask = guard_mask<T>(begin, length);
    return bits << begin & mask;
}

#endif  // ROWHAMMER_ADDR_HH_
