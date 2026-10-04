#!/bin/bash

g++ -static -I include -g -Wall -O3 -o ./attack-binaries/rrs_poc_sender ./attack-scripts/rrs-poc-sender.cc  ./attack-scripts/rowhammer-side.cc  util/m5/build/x86/out/libm5.a
g++ -static -I include -g -Wall -O3 -o ./attack-binaries/rrs_poc_receiver ./attack-scripts/rrs-poc-receiver.cc  ./attack-scripts/rowhammer-side.cc  util/m5/build/x86/out/libm5.a
echo "RRS POC recompiled"
