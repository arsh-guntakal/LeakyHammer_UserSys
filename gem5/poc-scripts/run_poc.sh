#!/bin/bash
# Run one proof-of-concept (POC) covert-channel transmission natively and
# decode the result.
#
# Usage (from anywhere, inside the container):
#   gem5/poc-scripts/run_poc.sh <rfm|dream|rrs> [ramulator-config.yaml]
#
# Output: gem5/results/poc/<name>.txt (+ m5out_<name>/), then a decoded summary.
# The optional second argument overrides the Ramulator config (e.g. to try a
# different RRS threshold without editing configs/rhsc/ramulator/rrs.yaml).
set -e

GEM5_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$GEM5_DIR"

name=${1:?usage: run_poc.sh <rfm|dream|rrs> [config.yaml]}
cfg=${2:-$GEM5_DIR/configs/rhsc/ramulator/$name.yaml}

case "$name" in
  rfm)   cmd="./attack-binaries/rfm_poc_sender;./attack-binaries/rfm_poc_receiver";     opts="20000 5 MICRO;20000 5 MICRO" ;;
  dream) cmd="./attack-binaries/dream_poc_sender;./attack-binaries/dream_poc_receiver"; opts="20000 5 0x00 UTECE;20000 5 0x00 UTECE" ;;
  rrs)   cmd="./attack-binaries/rrs_poc_sender;./attack-binaries/rrs_poc_receiver";     opts="20000 5 aa;20000 5 aa" ;;
  *) echo "unknown POC '$name' (use rfm, dream or rrs)"; exit 1 ;;
esac

mkdir -p results/poc
./build/X86/gem5.opt --outdir="results/poc/m5out_$name" \
  ./configs/deprecated/example/se.py --num-cpu=2 --cpu-type=O3CPU \
  --sys-clock=1GHz --cpu-clock=3GHz --mem-type=Ramulator2 --mem-size=32GB \
  --caches --l2cache --num-l2caches=1 --l1d_size=32kB --l1i_size=32kB \
  --l2_size=4MB --l1d_assoc=8 --l1i_assoc=8 --l2_assoc=16 --cacheline_size=64 \
  --ramulator-config="$cfg" --cmd="$cmd" --options="$opts" \
  > "results/poc/$name.txt" 2>&1

python3 result-scripts/decode_poc.py "results/poc/$name.txt"
