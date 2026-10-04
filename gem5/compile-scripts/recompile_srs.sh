#!/bin/bash
set -e

g++ -static -I include -g -Wall -O3 -o ./attack-binaries/srs_sender ./attack-scripts/rowhammer-srs-sender.cc ./attack-scripts/rowhammer-side.cc util/m5/build/x86/out/libm5.a
g++ -static -I include -g -Wall -O3 -o ./attack-binaries/srs_receiver ./attack-scripts/rowhammer-srs-receiver.cc ./attack-scripts/rowhammer-side.cc util/m5/build/x86/out/libm5.a
echo "SRS recompiled"
