#!/bin/bash

# get script dir
HOME_DIR=$(pwd)

ATTACK_SCRIPTS_DIR="$HOME_DIR/attack-scripts"
COMPILE_SCRIPTS_DIR="$HOME_DIR/compile-scripts"
PLOT_SCRIPTS_DIR="$HOME_DIR/plot-scripts"

ATTACK_BINARIES_DIR="$HOME_DIR/attack-binaries"
RESULTS_DIR="$HOME_DIR/results"
FIGURES_DIR="$HOME_DIR/figures"

# check if attack-binaries directory exists, if not create it
if [ ! -d "attack-binaries" ]; then
  echo "[INFO] Creating attack-binaries directory"
  mkdir attack-binaries
fi

# check if results directory exists, if not create it
if [ ! -d "results" ]; then
  echo "[INFO] Creating results directory"
  mkdir results
fi

# check if figures directory exists, if not create it
if [ ! -d "figures" ]; then
  echo "[INFO] Creating figures directory"
  mkdir figures
fi

echo "[INFO] Generating PRAC latency results (figure 2)"
# check if $FIGURES_DIR/figure2.pdf doesnt exist
if [ ! -f "$FIGURES_DIR/figure2.pdf" ]; then
  echo "[INFO] Figure 2 does not exist, generating it"
  sh $COMPILE_SCRIPTS_DIR/recompile-mr-latency.sh

  ./build/X86/gem5.opt ./configs/deprecated/example/se.py --num-cpu=1 --cpu-type=O3CPU --sys-clock=1GHz --cpu-clock=3GHz --mem-type=Ramulator2 --mem-size=8GB --caches --l2cache --num-l2caches=1 --l1d_size=32kB --l1i_size=32kB --l2_size=4MB --l1d_assoc=8 --l1i_assoc=8 --l2_assoc=16 --cacheline_size=64 --ramulator-config=$HOME_DIR/configs/rhsc/ramulator/prac.yaml '--cmd=./attack-binaries/mr_latency;' '--options=1600 2;' > $RESULTS_DIR/figure2.log

  echo "[INFO] Generating figure 2"
  python3 $PLOT_SCRIPTS_DIR/figure2_plotter.py $RESULTS_DIR/figure2.log $FIGURES_DIR/figure2.pdf

  echo "[COMPLETED] Figure 2 generated at $FIGURES_DIR/figure2.pdf"
else
  echo "[INFO] Figure 2 already exists, skipping generation"
fi

# check if $FIGURES_DIR/figure3.pdf doesnt exist
if [ ! -f "$FIGURES_DIR/figure3.pdf" ]; then
  echo "[INFO] Figure 3 does not exist, generating it"

  echo "[INFO] Generating PRAC POC results (figure 3)"
  sh $COMPILE_SCRIPTS_DIR/recompile-prac-poc.sh

  ./build/X86/gem5.opt ./configs/deprecated/example/se.py --num-cpu=2 --cpu-type=O3CPU --sys-clock=1GHz --cpu-clock=3GHz --mem-type=Ramulator2 --mem-size=8GB --caches --l2cache --num-l2caches=1 --l1d_size=32kB --l1i_size=32kB --l2_size=4MB --l1d_assoc=8 --l1i_assoc=8 --l2_assoc=16 --cacheline_size=64 --ramulator-config=$HOME_DIR/configs/rhsc/ramulator/prac.yaml --cmd="./attack-binaries/prac_poc_sender;./attack-binaries/prac_poc_receiver" --options="25000 5 aa;25000 5 aa;" > $RESULTS_DIR/figure3.log

  echo "[INFO] Generating figure 3"
  python3 $PLOT_SCRIPTS_DIR/figure3_plotter.py $RESULTS_DIR/figure3.log $FIGURES_DIR/figure3.pdf
  echo "[COMPLETED] Figure 3 generated at $FIGURES_DIR/figure3.pdf"

else
  echo "[INFO] Figure 3 already exists, skipping generation"
fi

# check if $FIGURES_DIR/figure6.pdf doesnt exist
if [ ! -f "$FIGURES_DIR/figure6.pdf" ]; then
  echo "[INFO] Figure 6 does not exist, generating it"

  echo "[INFO] Generating RFM POC results (figure 6)"
  sh $COMPILE_SCRIPTS_DIR/recompile-rfm-poc.sh

  ./build/X86/gem5.opt ./configs/deprecated/example/se.py --num-cpu=2 --cpu-type=O3CPU --sys-clock=1GHz --cpu-clock=3GHz --mem-type=Ramulator2 --mem-size=8GB --caches --l2cache --num-l2caches=1 --l1d_size=32kB --l1i_size=32kB --l2_size=4MB --l1d_assoc=8 --l1i_assoc=8 --l2_assoc=16 --cacheline_size=64 --ramulator-config=$HOME_DIR/configs/rhsc/ramulator/rfm.yaml --cmd="./attack-binaries/rfm_poc_sender;./attack-binaries/rfm_poc_receiver" --options="20000 5 aa;20000 5 aa;" > $RESULTS_DIR/figure6.log

  echo "[INFO] Generating figure 6"
  python3 $PLOT_SCRIPTS_DIR/figure6_plotter.py $RESULTS_DIR/figure6.log $FIGURES_DIR/figure6.pdf
  echo "[COMPLETED] Figure 6 generated at $FIGURES_DIR/figure6.pdf"

else
  echo "[INFO] Figure 6 already exists, skipping generation"
fi

# check if $FIGURES_DIR/srs_poc_figure.pdf doesnt exist
if [ ! -f "$FIGURES_DIR/srs_poc_figure.pdf" ]; then
  echo "[INFO] SRS POC figure does not exist, generating it"

  echo "[INFO] Generating SRS POC results"
  sh $COMPILE_SCRIPTS_DIR/recompile-srs-poc.sh

  ./build/X86/gem5.opt ./configs/deprecated/example/se.py --num-cpu=2 --cpu-type=O3CPU --sys-clock=1GHz --cpu-clock=3GHz --mem-type=Ramulator2 --mem-size=8GB --caches --l2cache --num-l2caches=1 --l1d_size=32kB --l1i_size=32kB --l2_size=4MB --l1d_assoc=8 --l1i_assoc=8 --l2_assoc=16 --cacheline_size=64 --ramulator-config=$HOME_DIR/configs/rhsc/ramulator/srs.yaml --cmd="./attack-binaries/srs_poc_sender;./attack-binaries/srs_poc_receiver" --options="20000 5 aa;20000 5 aa;" > $RESULTS_DIR/srs_poc.log

  echo "[INFO] Generating SRS POC figure"
  python3 $PLOT_SCRIPTS_DIR/srs_poc_plotter.py $RESULTS_DIR/srs_poc.log $FIGURES_DIR/srs_poc_figure.pdf
  echo "[COMPLETED] SRS POC figure generated at $FIGURES_DIR/srs_poc_figure.pdf"

else
  echo "[INFO] SRS POC figure already exists, skipping generation"
fi

