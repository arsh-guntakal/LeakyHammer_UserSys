# Changes to the vendored simulator

`gem5/` is **gem5 v24.0.0.0** (upstream: <https://github.com/gem5/gem5>, tag
`v24.0.0.0`) with the changes below. Everything else in this directory is
unmodified upstream. First-party code (attack programs, experiments, tests)
lives in `src/leakyhammer/`, not here.

Verify this list at any time with `tools/gem5-diff`, which compares the
tracked files against a fresh upstream checkout. If you change a vendored
file, add it here.

## Changed upstream files (14)

| Purpose | Files |
|---|---|
| **`mmap_atk` syscall (451).** Lets a simulated program map a page at an *arbitrary physical address*, which is how the attacker picks the DRAM row it hammers or probes. | `src/arch/x86/linux/syscall_tbl64.cc`, `src/sim/syscall_emul.hh`, `src/sim/process.cc`, `src/sim/process.hh` |
| **Ramulator2 as gem5's memory model.** `--mem-type=Ramulator2` and `--ramulator-config=<yaml>`. | `src/mem/SConscript`, `configs/common/MemConfig.py`, `configs/common/Options.py` (also adds `--m5-outdir`) |
| **Optional L3 cache** (unused by the LeakyHammer configs). | `configs/common/CacheConfig.py`, `configs/common/Caches.py`, `src/mem/XBar.py`, `src/cpu/BaseCPU.py` |
| **Per-run `/proc` and `/sys` for guest programs.** The redirect-path fix is ours: it used the wrong directory when `--m5-outdir` was set. | `configs/common/FileSystemConfig.py` |
| Debug print of the parsed arguments. | `configs/deprecated/example/se.py` |
| Extra ignore patterns. | `.gitignore` |

## Added files

| What | Where |
|---|---|
| Ramulator2 gem5 wrapper | `src/mem/Ramulator2.py`, `src/mem/ramulator2.cc`, `src/mem/ramulator2.hh`, `ext/ramulator2/SConscript` |
| Ramulator2 itself (a research fork, see below) | `ext/ramulator2/ramulator2/` |
| Ramulator YAML configs, one per defense | `configs/rhsc/ramulator/` (and `configs/rhsc/base_rhsc.py`) |
| An address-mapping patch for Ramulator | `ramulator-patches/0001-adds-an-easier-address-mapping.patch` |
| Build driver (called by `tools/build`) | `rebuild.sh` |

## Ramulator2 fork

`ext/ramulator2/ramulator2/` is **not** current CMU-SAFARI `ramulator2`: it is
the research lineage used by the RowHammer-defense papers (it has
`BHDRAMController`, the `DDR5-VRR` DRAM model, and the PRAC/RFM/RRS plugins)
and its layout differs from upstream `main`, so there is no clean upstream to
diff against. Treat it as source we maintain. Files we changed or added for
the DREAM-C work:

- `src/dram_controller/impl/plugin/dream.cpp`: the DREAM-C defense plugin
  (listed in `src/dram_controller/CMakeLists.txt`).
- `src/dram/impl/DDR5-VRR.cpp`: comment only; see `AGENTS.md` for why the
  DRFM timing inflation was reverted.

`rrs.cpp` (Randomized Row-Swap) came with the original LeakyHammer artifact.

## Why these live in the tree

The Ramulator plugins are compiled into `libramulator.so` by Ramulator's own
CMake, against its internal headers, so they stay beside it. (Compiling a
plugin from outside the tree works with one CMake edit, such as
`${LEAKYHAMMER_PLUGIN_DIR}/dream.cpp` in `target_sources`; we tested it, but
did not adopt it, to keep `libramulator.so` buildable from this directory
alone.) The guest attack programs, by contrast, never link against gem5: they
use only `gem5/m5ops.h` and `libm5.a`, so they live in the Python package.
