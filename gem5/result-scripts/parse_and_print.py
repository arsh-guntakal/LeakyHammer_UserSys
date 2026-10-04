import os
import re
import pandas as pd
import numpy as np

from run_config import *


def parse_simulations(preset, is_noise=False):
    RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES = get_preset_variables(preset, is_noise)
    results_list = []
    for rate in ACCESS_RATES:
        for pattern in DATA_PATTERNS:
            result_file = make_res_file(RESULT_DIR, preset, TXN_PERIOD, MSG_BYTES, pattern, rate)
            if not os.path.exists(result_file):
                continue
            result = parse_file(result_file)
            if EARLY_TERMINATE and result.errors >= 0:
                print(f"[INFO] can early terminate ")
                slurm_job_name = make_stat_str(preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
                jobid = get_jobid_with_name(slurm_job_name)
                if jobid != -1:
                    print(f"[INFO] Killing job {slurm_job_name} with ID {jobid}")
                    subprocess.run(["scancel", str(jobid)])
            results_list.append({
                "rate": rate,
                "pattern": pattern,
                "sent": result.send_binary,
                "received": result.recv_binary,
                "time": result.txn_time,
                "errors": result.errors
            })
    
    df = pd.DataFrame(results_list)
    #print(f"Parsed {len(df)} runs")
    noise_prefix = "noise_" if is_noise else ""
    df.to_csv(f"{BASE_DIR}/results/{noise_prefix}ber_{preset.lower()}.csv", index=False)

def entropy(p):
    return -1 * p * np.log2(p) - (1 - p) * np.log2(1 - p)

def print_results(preset):
    df = pd.read_csv(f"{BASE_DIR}/results/ber_{preset.lower()}.csv",
                     dtype={'sent': str, 'received': str})
    avg_time = df['time'].mean()
    runtime_second = avg_time / 1000 / 1000 / 1000
    raw_bit_rate = (MSG_BYTES * 8) / runtime_second / 1024
    avg_error_rate = df['errors'].mean() / (MSG_BYTES * 8)
    print(f"{preset} Raw Bit Rate (Kbps): {raw_bit_rate:.3f}, mean BER: {avg_error_rate:.4f}")

def print_results_noise(preset):
    df = pd.read_csv(f"{BASE_DIR}/results/noise_ber_{preset.lower()}.csv",
                     dtype={'sent': str, 'received': str})
    avg_time = df['time'].mean()
    avg_error_rate = df['errors'].mean() / (MSG_BYTES * 8)
    runtime_second = avg_time / 1000 / 1000 / 1000
    raw_bit_rate = (MSG_BYTES * 8) / runtime_second / 1024
    channel_capacity = raw_bit_rate * (1- entropy(avg_error_rate))

    print(f"{preset} Raw Bit Rate (Kbps):", raw_bit_rate)
    print(f"{preset} Channel Capacity (Kbps):", channel_capacity)

def main():
    parse_simulations("PRAC")
    parse_simulations("RFM")
    parse_simulations("DREAM")
    print("Results for baseline PRAC, RFM, and DREAM:")
    print_results("PRAC")
    print_results("RFM")
    print_results("DREAM")
    
    parse_simulations("PRAC", is_noise=True)
    parse_simulations("RFM", is_noise=True)
    parse_simulations("DREAM", is_noise=True)
    parse_simulations("SRS", is_noise=True)

    print("\nNoise channel summary:")
    print_results_noise("PRAC")
    print_results_noise("RFM")
    print_results_noise("DREAM")
    print_results_noise("SRS")

    # run python3 plot-scripts/figure7_plotter.py results/noise_ber_rfm.csv figures/figure7.pdf 100 RFM
    subprocess.run([
        "python3",
        f"{BASE_DIR}/plot-scripts/figure7_plotter.py",
        f"{BASE_DIR}/results/noise_ber_rfm.csv",
        f"{BASE_DIR}/figures/figure7.pdf",
        str(MSG_BYTES),
        "RFM"
    ])

    # DREAM uses same plotter shape as RFM but is labeled distinctly
    subprocess.run([
        "python3",
        f"{BASE_DIR}/plot-scripts/figure7_plotter.py",
        f"{BASE_DIR}/results/noise_ber_dream.csv",
        f"{BASE_DIR}/figures/figure7_dream.pdf",
        str(MSG_BYTES),
        "DREAM"
    ])

    subprocess.run([
        "python3",
        f"{BASE_DIR}/plot-scripts/figure7_plotter.py",
        f"{BASE_DIR}/results/noise_ber_srs.csv",
        f"{BASE_DIR}/figures/figure7_srs.pdf",
        str(MSG_BYTES),
        "SRS"
    ])

    # run python3 plot-scripts/figure4_plotter.py results/noise_ber_prac.csv figures/figure4.pdf 100
    subprocess.run([
        "python3",
        f"{BASE_DIR}/plot-scripts/figure4_plotter.py",
        f"{BASE_DIR}/results/noise_ber_prac.csv",
        f"{BASE_DIR}/figures/figure4.pdf",
        str(MSG_BYTES)
    ])


if __name__ == "__main__":
    main()
