# Tests

Run everything with `uv run pytest`. Tiers that need the simulator skip
themselves when gem5 is not built, so this works in a fresh container.

| Tier | Marker | Location | Needs gem5 | What it checks |
|---|---|---|---|---|
| Unit | `unit` | `tests/`, `tests/experiments/` | no | Pure logic, with `Simulation.run` faked |
| Integration | `integration`, `slow` | `tests/integration/` | yes | The core library against a real simulator |
| Experiment | `experiment`, `slow` | `tests/experiments/` | yes | An experiment end to end |

`regression` marks a test that guards a fixed bug (the old failure is in its
docstring). Every test needs at least one marker; `conftest.py` enforces it.

No data files are committed (`tests/data/` is gitignored): the fixtures in
`conftest.py` build logs and tables in the formats the real programs print.
