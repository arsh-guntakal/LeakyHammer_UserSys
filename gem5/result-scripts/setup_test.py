import os
import time
import argparse

from run_config import *


def create_run_scripts(command, sim_result_file_path, slurm_job_name):
    if SKIP_EXISTING:
        result = parse_file(sim_result_file_path)
        if result.errors >= 0:
            print(f"[INFO] {slurm_job_name} already exists.")
            return ""
    script_content = ""
    if SLURM:
        script_content = f"{CMD_HEADER}\n{command}\n"
    else:
        script_content = f"{CMD_HEADER}\n{command} > {sim_result_file_path} 2>&1\n"
    if CONTAINER and SLURM:
        script_content = f"{CMD_HEADER}\n{CONTAINER_COMMAND} {CONTAINER_CHECK} {CONTAINER_COMMAND} {CONTAINER_LOAD}\n{CONTAINER_COMMAND} run --rm {USER_FLAG} -v {BASE_DIR}:/app  {CONTAINER_IMAGE} \'{command}\'\n"
    elif CONTAINER and not SLURM:
        sim_result_file_path_app = sim_result_file_path.replace(BASE_DIR, "/app")
        script_content = f"{CMD_HEADER}\n{CONTAINER_COMMAND} {CONTAINER_CHECK} {CONTAINER_COMMAND} {CONTAINER_LOAD}\n{CONTAINER_COMMAND} run --rm {USER_FLAG} -v {BASE_DIR}:/app  {CONTAINER_IMAGE} \'{command} > {sim_result_file_path_app} 2>&1\'\n"
    script_path = f"{BASE_DIR}/run_scripts/{slurm_job_name}.sh"
    with open(script_path, "w") as script_file:
        script_file.write(script_content)
    os.chmod(script_path, 0o755)
    return script_path
    

def get_baseline_run_commands():
    run_scripts = []
    test_presets = ["PRAC", "RFM", "DREAM", "SRS"]
    rate = 0
    for preset in test_presets:
      RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES = get_preset_variables(preset)
      if not os.path.isdir(RESULT_DIR):
          os.makedirs(RESULT_DIR)
      if not os.path.isdir(f"{RESULT_DIR}/err"):
          os.makedirs(f"{RESULT_DIR}/err")
          print(f"[INFO] Created error directory: {RESULT_DIR}/err")

      for pattern in DATA_PATTERNS:
          dir_path = make_temp_dir(RESULT_DIR, preset, TXN_PERIOD, MSG_BYTES, pattern, rate) 
          if not os.path.isdir(dir_path):
              os.makedirs(dir_path)

      for pattern in DATA_PATTERNS:
          dir_path = make_temp_dir(RESULT_DIR, preset,TXN_PERIOD, MSG_BYTES, pattern, rate) 
          result_file = make_res_file(RESULT_DIR, preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
          err_file = make_err_file(RESULT_DIR, preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
          slurm_job_name = make_stat_str(preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
          command = CMD_STR.format(
              cfg_file=CFG_FILE,
              output_dir=dir_path,
              txn_window=TXN_PERIOD,
              msg_len=MSG_BYTES,
              data_pattern=pattern,
              sender=SENDER,
              receiver=RECEIVER,
              access_rate=rate
          )
          # if container is enabled change all BASE_DIR paths to app/ paths
          if CONTAINER:
            command = command.replace(BASE_DIR, "/app")
          script_path = create_run_scripts(command, result_file,slurm_job_name)
          if script_path:
            wrapper_command = ""
            if SLURM:
                wrapper_command = f"{SBATCH_CMD} --chdir={BASE_DIR} "
                wrapper_command += f"--output={result_file} --error={err_file} "
                wrapper_command += f"--job-name='{slurm_job_name}' --partition={PARTITION_NAME} "
                wrapper_command += f"{script_path}"
            else:
                wrapper_command = f"sh {script_path}"
            run_scripts.append(wrapper_command)
          #run_simulation(command, result_file, slurm_job_name)
    return run_scripts

def get_noise_run_commands():
    run_scripts = []
    test_presets = ["PRAC", "RFM", "DREAM", "SRS"]
    for preset in test_presets:
      RESULT_DIR, CFG_FILE, SENDER, RECEIVER, TXN_PERIOD, ACCESS_RATES = get_preset_variables(preset, is_noise=True)
      if not os.path.isdir(RESULT_DIR):
          os.makedirs(RESULT_DIR)
          print(f"[INFO] Created result directory: {RESULT_DIR}")
      if not os.path.isdir(f"{RESULT_DIR}/err"):
          os.makedirs(f"{RESULT_DIR}/err")
          print(f"[INFO] Created error directory: {RESULT_DIR}/err")

      for rate in ACCESS_RATES:
      
        for pattern in DATA_PATTERNS:
            dir_path = make_temp_dir(RESULT_DIR, preset, TXN_PERIOD, MSG_BYTES, pattern, rate) 
            if not os.path.isdir(dir_path):
                os.makedirs(dir_path)

        for pattern in DATA_PATTERNS:
            dir_path = make_temp_dir(RESULT_DIR, preset,TXN_PERIOD, MSG_BYTES, pattern, rate) 
            result_file = make_res_file(RESULT_DIR, preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
            err_file = make_err_file(RESULT_DIR, preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
            slurm_job_name = make_stat_str(preset,TXN_PERIOD, MSG_BYTES, pattern, rate)
            attack_period = TXN_PERIOD * MSG_BYTES * 8 * 1.5
            noise_generator = f"{BASE_DIR}/attack-binaries/mr_noise"
            command = NOISE_CMD_STR.format(
                cfg_file=CFG_FILE,
                output_dir=dir_path,
                txn_window=TXN_PERIOD,
                msg_len=MSG_BYTES,
                data_pattern=pattern,
                sender=SENDER,
                receiver=RECEIVER,
                attack_period=attack_period,
                noise_generator=noise_generator,
                access_rate=rate
            )
            # if container is enabled change all BASE_DIR paths to app/ paths
            if CONTAINER:
                command = command.replace(BASE_DIR, "/app")
            script_path = create_run_scripts(command, result_file,slurm_job_name)
            if script_path:
                wrapper_command = ""
                if SLURM:
                    wrapper_command = f"{SBATCH_CMD} --chdir={BASE_DIR} "
                    wrapper_command += f"--output={result_file} --error={err_file} "
                    wrapper_command += f"--job-name='{slurm_job_name}' --partition={PARTITION_NAME} "
                    wrapper_command += f"{script_path}"
                else:
                    wrapper_command = f"sh {script_path}"
                run_scripts.append(wrapper_command)
            #run_simulation(command, result_file, slurm_job_name)
    return run_scripts

argparser = argparse.ArgumentParser(
    prog="RunArtifact",
    description="Run gem5+ramulator2 simulations for the LeakyHammer attack on personal computers and slurm clusters.",
)

argparser.add_argument("-s", "--slurm", action="store_true", help="Run the simulations using slurm", default=False)
argparser.add_argument("-c", "--container", action="store_true", help="Run the simulations in a container using podman or docker", default=False)
argparser.add_argument("-cc", "--container_command", type=str, help="Run the simulations in a container using podman or docker", default="podman")

args = argparser.parse_args()

SLURM = args.slurm
CONTAINER = args.container
CONTAINER_COMMAND = args.container_command


UID = os.getuid()
GID = os.getgid()
USER_FLAG = f"--user {UID}:{GID}"


os.system(f"rm -r {BASE_DIR}/run_scripts")
os.system(f"mkdir -p {BASE_DIR}/run_scripts")

cmds = get_baseline_run_commands()
noise_cmds = get_noise_run_commands()
cmds.extend(noise_cmds)

with open("run.sh", "w") as f:
    # f.write(f"{CMD_HEADER}\n")
    for cmd in cmds:
        f.write(f"{cmd}\n")

os.system("chmod uog+x run.sh")

