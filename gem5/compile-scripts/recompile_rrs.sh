#!/bin/bash
set -e

g++ -static -I include -g -Wall -O3 -o ./attack-binaries/rrs_sender ./attack-scripts/rowhammer-rrs-sender.cc ./attack-scripts/rowhammer-side.cc util/m5/build/x86/out/libm5.a
g++ -static -I include -g -Wall -O3 -o ./attack-binaries/rrs_receiver ./attack-scripts/rowhammer-rrs-receiver.cc ./attack-scripts/rowhammer-side.cc util/m5/build/x86/out/libm5.a
echo "RRS recompiled"
