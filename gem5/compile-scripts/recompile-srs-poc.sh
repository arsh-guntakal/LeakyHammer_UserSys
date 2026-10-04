#!/bin/bash

g++ -static -I include -g -Wall -O3 -o ./attack-binaries/srs_poc_sender ./attack-scripts/srs-poc-sender.cc  ./attack-scripts/rowhammer-side.cc  util/m5/build/x86/out/libm5.a
g++ -static -I include -g -Wall -O3 -o ./attack-binaries/srs_poc_receiver ./attack-scripts/srs-poc-receiver.cc  ./attack-scripts/rowhammer-side.cc  util/m5/build/x86/out/libm5.a
echo "SRS POC recompiled"
