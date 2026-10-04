#!/bin/bash

# This script is used to rebuild ramulator and gem5
# arguments are passed to the script as follows:
# --ramulator: rebuild ramulator
# --gem5: rebuild gem5
# --all: rebuild both ramulator and gem5

# Parallel jobs; override with e.g. JOBS=32 ./rebuild.sh --all
RAMULATOR_JOBS=${JOBS:-8}
GEM5_JOBS=${JOBS:-2}

rebuild_ramulator() {
    echo "Rebuilding ramulator"
    cd ext/ramulator2/ramulator2
    # check if build directory exists, if not create it
    if [ ! -d "build" ]; then
        mkdir build
    fi
    cd build
    cmake -DCMAKE_BUILD_TYPE=Debug ..
    make -j"$RAMULATOR_JOBS" || exit 1
    cp ./ramulator2 ../ramulator2
    echo "Ramulator rebuilt successfully"
    cd ../../../
}

rebuild_gem5() {
    echo "Rebuilding gem5"
    # gem5 embeds the *system* python3 (via python3-config), so scons must also
    # run under /usr/bin/python3. A uv/venv python3 here makes gem5.opt abort at
    # build time with "No module named '_contextvars'". scons itself is pure
    # python, so borrow it from the uv venv's site-packages.
    VENV_SITE=$(ls -d "$(dirname "$0")"/../.venv/lib/python3.*/site-packages 2>/dev/null | head -1)
    SCONS_BIN=$(ls "$(dirname "$0")"/../.venv/bin/scons 2>/dev/null || command -v scons)
    PYTHONPATH="$VENV_SITE:$PYTHONPATH" /usr/bin/python3 "$SCONS_BIN" build/X86/gem5.opt -j"$GEM5_JOBS" || exit 1
    echo "gem5 rebuilt successfully"
    PYTHONPATH="$VENV_SITE:$PYTHONPATH" /usr/bin/python3 "$SCONS_BIN" -C util/m5 build/x86/out/m5 || exit 1
    echo "m5 util built successfully"
}

clean_all(){
    echo "Cleaning gem5"
    rm -r build
    echo "Cleaning ramulator"
    cd ext/ramulator2/ramulator2/
    rm -r build
    echo "Done"
}

case "$1" in
    --ramulator)
        rebuild_ramulator
        ;;
    --gem5)
        rebuild_gem5
        ;;
    --all)
        rebuild_ramulator
        rebuild_gem5
        ;;
    --clean) 
        clean_all
        ;;
    *)
        echo "Usage: $0 {--ramulator|--gem5|--all}"
        exit 1
        ;;
esac

exit 0