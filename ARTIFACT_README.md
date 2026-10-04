# Artifact for LeakyHammer

This repository contains the source code of LeakyHammer, our [MICRO'25 paper](https://arxiv.org/pdf/2503.17891). 

LeakyHammer is a new class of attacks that leverage the RowHammer mitigation-induced memory latency differences to establish communication channels and leak secrets.

> F. Nisa Bostanci, Oguzhan Canpolat, Ataberk Olgun, İsmail Emir Yüksel, Konstantinos Kanellopoulos, Mohammad Sadrosadati, A. Giray Yağlıkçı, Onur Mutlu. "Understanding and Mitigating Covert and Side Channel Vulnerabilities Introduced by RowHammer Defenses", MICRO 2025.


## 1. Prerequisites & System Requirements:
We strongly recommend using our container image to satisfy all dependencies with the correct versions selected. Our scripts already include instructions to build the image from our Dockerfile. 

### Software Requirements for Docker-based installation:
``` 
- Docker
- curl
- tar
- Debian-based Linux distribution
```
Tested versions and distributions:
```
- Docker version 28.1.1+1, build 068a01e
- Podman 4.5.2
- curl 7.81.0   
- tar (GNU tar) 1.34
- Kernel: 5.15.0-56-generic 
- Dist: Ubuntu SMP 22.04.1 LTS (Jammy Jellyfish)
                    
```

The Docker image contain all the necessary software to compile and run gem5+Ramulator2 experiments, therefore no additional system-level installation step is required. 

### Getting started:

Our container-based setup script (`container_setup.sh`) already builds the container image and sets up the environment without any additional steps (see instructions under Building The Simulators). To build the container image manually:

```bash 
[docker/podman] build . --no-cache --pull -t leakyhammer_artifact
```

#### Getting started without Docker:

For artifact evaluation purposes (i.e., reproducing figures exactly matching with the ones presented in the paper), we **strongly recommend** using the container image to build the resources and run the experiments. 

To get started with the simulators for further analyses and experiments, you can set up the environment for native execution using the `ae_install_requirements.sh` script and install all dependencies: 

```bash
./ae_install_requirements.sh
```

If supported (e.g., executing in a system with Linux 20.04), you can match all package versions by executing the following command instead of the previous command:

```bash
./ae_install_requirements.sh true
```

To install only python3 dependencies with pip manually:

```bash
python3 -m pip install -r requirements.txt
```

## 2. Building The Simulators
The following steps prepares the repository for the main experiments. 

### Using Docker
The `container_setup.sh` script 1) builds the docker image and the simulators (gem5 and Ramulator2), 2) runs small experiments, 3) compiles the attack scripts and 4) saves the Docker image for future use.

```bash
cd LeakyHammer
./container_setup.sh docker
```

### Without Docker

The `native_setup.sh` script 1) builds the simulators (gem5 and Ramulator2), 2) runs small experiments, and 3) compiles the attack scripts.


```bash
cd LeakyHammer
./native_setup.sh
```

## 3. Running The Artifact

The following instructions assume the reader is using Docker. If the reader is not using Docker, please refer to the instructions at the end of the section (:fast_forward:).

:warning: We suggest using ```tmux``` or similar tools that enable persistent bash sessions to avoid any interruptions during the execution of the scripts.

### Configuring the scripts
You can review and update script configurations set in the `gem5/result-scripts/run_config.py` based on the selected execution environment. You can specify the number of concurrently running jobs, user and partition names for slurm-based execution.

You can quickly review the existing settings:

```bash
head -n36 ./gem5/result-scripts/run_config.py
```

### Slurm-based execution
We strongly suggest using a Slurm-based infrastructure to enable running experiments in bulk. 


Use the following command to schedule Slurm jobs for experiments. 


```bash
sh gem5/run_parallel_slurm_container.sh docker
```

This script creates the ```results``` directory and ```prac``` and ```rfm``` subdirectories for the covert channel attacks. Within each subdirectory, there should be two directories ```baseline```, and ```noise``` for the experiment results.

The script then starts submitting Slurm jobs. Based on the maximum concurrently running (or scheduled) Slurm job limitation, it may stop and retry after an interval (configurable in ```run_config.py```). It terminates after submitting all jobs.

### Local machine-based execution
Use the following command to run all experiments using ThreadPoolExecutor. The number of concurrent workers is configurable in ```run_config.py```.

```bash
sh gem5/run_parallel_local_container.sh podman
```

The script creates and uses the same directories as given above. It terminates after all experiments are completed.

---
:fast_forward: The reader can also run experiments **without Docker** by using `gem5/run_parallel_local.sh` (for local execution) and `gem5/run_parallel_slurm.sh` (for Slurm-based execution) scripts.

:warning: Note that running the experiments in without the provided container image might compile the attack scripts with different compiler versions. This might result in slightly different data points shown in the figures based on your system configurations (e.g., compiler version) but it does not change the key observations.

### ***Experiment completion***

Each experiment for provided configurations takes at most 1 hour. Executing all jobs can take 2-4 hours in a compute cluster, depending on the cluster load. The reader can check the results and statistics generated by the experiments by checking the ```results/``` directory. Each experiment generates a txt file that contains its output in (```results/<config>/<experiment_type>/```). 

For Slurm-based execution, check ```results/<config>/<experiment_type>/err/``` for error files if needed.

### Obtaining figures and key results
To plot all figures at once using a docker image, the reader can use the ```plot_figures_container.sh``` script.

``` bash
sh gem5/plot_figures_container.sh docker
```

In native environment, use:
```bash
sh gem5/plot_figures.sh
```

This script plots all figures under ```gem5/figures/``` directory and prints out a summary of the results.

This command creates the following plots and their related results that are mentioned in the paper:

1. ```figure2.pdf```: Figure 2
2. ```figure3.pdf```: Figure 3
3. ```figure4.pdf```: Figure 4
4. ```figure6.pdf```: Figure 6
5. ```figure7.pdf```: Figure 7



## 4. File Structure

```
.
├── ae_install_requirements.sh
├── container_setup.sh                              # script for container-based execution setup
├── Dockerfile                                      
├── gem5
│   ├── attack-scripts                              # attack codes
│   ├── ...
│   ├── compile_attack_scripts.sh                   # script to compile all attacks
│   ├── ...
│   ├── ext
│   │   ├ramulator2                                 # Ramulator2 source code
│   │   │ ...
│   ├── get_all_results_local.sh                    # script that runs short-running experiments
│   ├── ...
│   ├── plot_figures_container.sh                   # script to plot all figures
│   ├── plot-scripts                                # plotting scripts
│   ├── ...
│   ├── rebuild.sh                                  # rebuild script for simulators
│   ├── ...
│   ├── result-scripts                              # scripts to set up experiment directories and create runner scripts
│   ├── results                                     # contains all results
│   ├── run_parallel_local_container.sh             # for running parallel jobs in local machine
│   ├── run_parallel_slurm_container.sh             # for running Slurm jobs in bulk
│   ├── ...
│   ├── src                                         # gem5 source code
│   ├── ...
├── native_setup.sh                                 # build script for native environment
├── README.md                                       # This file
└── requirements.txt                                # python requirements
```

## 5. Contact
Nisa Bostanci (nisa.bostanci [at] safari [dot] ethz [dot] ch)
