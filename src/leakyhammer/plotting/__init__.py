"""Matplotlib plotters for the LeakyHammer figures."""

import matplotlib

# Force the non-interactive backend before any submodule imports pyplot, so
# plotting works headless (CI, containers, tests) without a display.
matplotlib.use("Agg")
