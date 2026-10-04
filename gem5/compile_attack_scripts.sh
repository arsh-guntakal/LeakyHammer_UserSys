#!/bin/bash

# get script dir
HOME_DIR=$(pwd)

COMPILE_SCRIPTS_DIR="$HOME_DIR/compile-scripts"

sh $COMPILE_SCRIPTS_DIR/recompile-rfm-poc.sh
sh $COMPILE_SCRIPTS_DIR/recompile-prac-poc.sh
sh $COMPILE_SCRIPTS_DIR/recompile-mr-latency.sh
sh $COMPILE_SCRIPTS_DIR/recompile_noise.sh
sh $COMPILE_SCRIPTS_DIR/recompile_prac.sh
sh $COMPILE_SCRIPTS_DIR/recompile_rfm.sh
sh $COMPILE_SCRIPTS_DIR/recompile_dream.sh
sh $COMPILE_SCRIPTS_DIR/recompile_srs.sh
