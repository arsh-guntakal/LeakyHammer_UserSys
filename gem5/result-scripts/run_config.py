import os
import re
import subprocess

class SimResult:
    def __init__(self):
        self.send_binary = ""
        self.recv_binary = ""
        self.txn_time = -1
        self.errors = -1

SECONDS = 1
MINUTES = 60
HOURS = MINUTES * 60

# Maximum number of runs to be running/be scheduled at the same time for slurm
MAX_RUNS = 1000
# Slurm retry interval for submitting jobs
SUBMIT_RETRY_INTEVAL = 1 * MINUTES
# Slurm job submission delay
SLURM_SUBMIT_DELAY = 0.1 
# skipping existing runs when rerunning failed experiments
SKIP_EXISTING = True
# do not change
EARLY_TERMINATE = False
# Number of threads used for the personal computer runs
PERSONAL_RUN_THREADS = 4
# Slurm username
SLURM_USERNAME = "$USER" 
# Slurm partition name
PARTITION_NAME = "cpu_part"
# Slurm node exclude list
EXCLUDE_LIST = "kratos10,kratos17"

# legacy
GARBAGE_COLLECTOR_INTERVAL = 1 * MINUTES

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # go one level up to the gem5
ROOT_DIR = os.path.dirname(BASE_DIR)  # go one level up to the root of the repository
REFRESH_WINDOW_NS = 32_000_000
# ACCESS_RATES = range(2000, 20000, 250)
# ACCESS_RATES = range(0,  500, 10)
# ACCESS_RATES = [0]
NUM_PRESET = 2
ERROR_IDX = 0
MSG_LEN_IDX = 1

MSG_BYTES = 100
DATA_PATTERNS = ["0x00", "0x55", "0xAA", "0xFF"]



SBATCH_CMD = f"sbatch --cpus-per-task=1 --nodes=1 --ntasks=1 --mem=16G --exclude={EXCLUDE_LIST}"
CONTAINER_CHECK = f"image inspect leakyhammer_artifact:latest >/dev/null 2>&1 || "
CONTAINER_LOAD =  f"load --quiet -i {ROOT_DIR}/leakyhammer_artifact.tar"
CONTAINER_IMAGE = "leakyhammer_artifact"

CMD_HEADER = "#! /bin/bash"

# returns RESULT_DIR, CFG_FILE, TXN_PERIOD
def get_preset_variables(preset, is_noise=False):
  result_subdir = "noise" if is_noise else "baseline"
  ACCESS_RATES = [0]
  if preset == "PRAC":
      RESULT_DIR = f"{BASE_DIR}/results/{preset.lower()}/{result_subdir}"
      CFG_FILE = f"{BASE_DIR}/configs/rhsc/ramulator/prac.yaml"
      SENDER = f"{BASE_DIR}/attack-binaries/prac_sender"
      RECEIVER = f"{BASE_DIR}/attack-binaries/prac_receiver"
      TXN_PERIOD = 25000
      if is_noise:
          # Diverse subset: endpoints (275, 1975) and target point 475 (~88% intensity)
          ACCESS_RATES = [275, 475, 1075, 1975]
      return RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES
  elif preset == "RFM":
      RESULT_DIR = f"{BASE_DIR}/results/{preset.lower()}/{result_subdir}"
      CFG_FILE = f"{BASE_DIR}/configs/rhsc/ramulator/rfm.yaml"
      SENDER = f"{BASE_DIR}/attack-binaries/rfm_sender"
      RECEIVER = f"{BASE_DIR}/attack-binaries/rfm_receiver"
      TXN_PERIOD = 20000
      if is_noise:
          # Diverse subset: endpoints (200, 325) and target point 263 (~50% intensity)
          ACCESS_RATES = [200, 263, 325]
      return RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES
  elif preset == "DREAM":
      RESULT_DIR = f"{BASE_DIR}/results/{preset.lower()}/{result_subdir}"
      CFG_FILE = f"{BASE_DIR}/configs/rhsc/ramulator/dream.yaml"
      SENDER = f"{BASE_DIR}/attack-binaries/dream_sender"
      RECEIVER = f"{BASE_DIR}/attack-binaries/dream_receiver"
      # 20000 ns is the empirically optimal window for DREAM with the
      # paper-faithful cross-bank shared DCT plugin. We swept 25000 once
      # as a sanity check (2026-04-25): raw rate dropped 20% as expected,
      # but baseline BER nearly doubled (0.028 -> 0.050) because the
      # receiver's probe loop has more time to self-trigger the shared
      # gang counter. Net capacity dropped from 16.0 -> 13.2 Kbps. Don't
      # raise this casually -- see chat log / AGENTS.md changelog.
      TXN_PERIOD = 20000
      if is_noise:
          ACCESS_RATES = [200, 263, 325]
      return RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES
  elif preset == "RRS":
      RESULT_DIR = f"{BASE_DIR}/results/{preset.lower()}/{result_subdir}"
      CFG_FILE = f"{BASE_DIR}/configs/rhsc/ramulator/rrs.yaml"
      SENDER = f"{BASE_DIR}/attack-binaries/rrs_sender"
      RECEIVER = f"{BASE_DIR}/attack-binaries/rrs_receiver"
      TXN_PERIOD = 20000
      if is_noise:
          ACCESS_RATES = [200, 263, 325]
      return RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES

CMD_ARGS = [
    f"{BASE_DIR}/build/X86/gem5.opt",
    f"{BASE_DIR}/configs/deprecated/example/se.py",
    "--num-cpu=2",
    "--cpu-type=O3CPU",
    "--sys-clock=1GHz",
    "--cpu-clock=3GHz",
    "--mem-type=Ramulator2",
    # 32 GB needed for the DREAM matrix sender's two-bank gang collision
    # (row_b can be up to 65535, which puts the physical address at ~16 GB
    # under DDR5_16Gb_x8). PRAC/RFM senders/receivers and the noise generator
    # all pin (bg=7, ba=3, row=0..a few), whose addresses fit comfortably in
    # 8 GB or 32 GB -- the mem-size only sets the address-space ceiling and
    # doesn't affect simulated DRAM timing, so PRAC/RFM results are invariant.
    "--mem-size=32GB",
    "--caches",
    "--l2cache",
    "--num-l2caches=1",
    "--l1d_size=32kB",
    "--l1i_size=32kB",
    "--l2_size=4MB",
    "--l1d_assoc=8",
    "--l1i_assoc=8",
    "--l2_assoc=16",
    "--cacheline_size=64",
    "--ramulator-config={cfg_file}",
    "--m5-outdir={output_dir}",
    '--cmd="{sender};{receiver}"',
    '--options="{txn_window} {msg_len} {data_pattern};{txn_window} {msg_len} {data_pattern}"',
]

NOISE_CMD_ARGS = [
    f"{BASE_DIR}/build/X86/gem5.opt",
    f"{BASE_DIR}/configs/deprecated/example/se.py",
    "--num-cpu=3",
    "--cpu-type=O3CPU",
    "--sys-clock=1GHz",
    "--cpu-clock=3GHz",
    "--mem-type=Ramulator2",
    "--mem-size=32GB",
    "--caches",
    "--l2cache",
    "--num-l2caches=1",
    "--l1d_size=32kB",
    "--l1i_size=32kB",
    "--l2_size=4MB",
    "--l1d_assoc=8",
    "--l1i_assoc=8",
    "--l2_assoc=16",
    "--cacheline_size=64",
    "--ramulator-config={cfg_file}",
    "--m5-outdir={output_dir}",
    '--cmd="{sender};{receiver};{noise_generator}"',
    '--options="{txn_window} {msg_len} {data_pattern};{txn_window} {msg_len} {data_pattern};{attack_period} 32 {access_rate}"',
]

CMD_STR = " ".join(CMD_ARGS)
NOISE_CMD_STR = " ".join(NOISE_CMD_ARGS)

RESULT_PARSE_ERROR = 30
FIX_YOUR_CODE_ERROR = 31



def make_stat_str(preset, txn_period, msg_bytes, data_pattern, rate):
    return f"t{txn_period}_{msg_bytes}b_p{data_pattern}_r{rate}d_{preset.lower()}"

def make_temp_dir(result_dir,preset, txn_period, msg_bytes, data_pattern, rate):
    return f"{result_dir}/tmpfs/tmp_{make_stat_str(preset, txn_period, msg_bytes, data_pattern, rate)}"

def make_res_file(result_dir, preset, txn_period, msg_bytes, data_pattern, rate):
    return f"{result_dir}/{make_stat_str(preset,txn_period, msg_bytes, data_pattern, rate)}.txt"

def make_err_file(result_dir, preset, txn_period, msg_bytes, data_pattern, rate):
    return f"{result_dir}/err/{make_stat_str(preset,txn_period, msg_bytes, data_pattern, rate)}.err"

def parse_file(sim_result_file_path):
    result = SimResult()
    if not os.path.exists(sim_result_file_path):
        return result
    with open(sim_result_file_path, "r", encoding="utf-8", errors="replace") as file:
        content = file.read()
        send_match = re.search(r"\[(?:[A-Z]+-)?SEND\] Binary: (\d+)", content)
        if send_match:
            result.send_binary = str(send_match.group(1))
        recv_match = re.search(r"\[(?:[A-Z]+-)?RECV\] Binary: (\d+)", content)
        if recv_match:
            result.recv_binary = str(recv_match.group(1))
        txn_match = re.search(r"\[(?:[A-Z]+-)?RECV\] Received in (\d+) ns", content)
        if txn_match:
            result.txn_time = int(txn_match.group(1))
        if len(result.send_binary) != len(result.recv_binary):
            result.errors = -FIX_YOUR_CODE_ERROR
            return result
        if result.send_binary == "" or result.recv_binary == "":
            result.errors = -RESULT_PARSE_ERROR
            return result
        errors = 0
        for i in range(len(result.send_binary)):
            if result.send_binary[i] != result.recv_binary[i]:
                errors += 1
        result.errors = errors
    return result


def get_jobid_with_name(name):
    cmd = f'sacct --user=$USER --state="PENDING,RUNNING" --format="JobID,JobName%50" | grep {name} | awk \'{{print $1}}\''
    res = subprocess.getoutput(cmd)
    if len(res) == 0:
        return -1
    jobid = -1
    try:
        jobid = int(res)
    except:
        print(f"[INFO] Cannot kill {name}. Potential cause could be multiple runs with the same name existing.")
        print(f"[INFO] Command result was: {res}")
    return jobid

def get_job_count():
    try:
        return int(subprocess.getoutput(f"squeue -u $USER -h -t pending,running -r | wc -l"))
    except:
        return MAX_RUNS # prevent new runs from being issued until we get the correct count

def kill_job_with_name(name):
    jobid = get_jobid_with_name(name)
    if jobid >= 0:
        os.system(f"scancel {jobid}")
