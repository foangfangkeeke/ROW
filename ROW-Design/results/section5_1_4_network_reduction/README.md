# 5.1.4 Network Reduction Results

This directory is produced by `tools/run_5_1_4_network_reduction.py`.

Default experiment design:

- Instances: R04-R10 and Sioux_Falls_30OD, Y1/S10.
- Variants: unreduced and R1-R3 reduced networks.
- Method for optional timing comparison: BD-P-NR.

## Reproduction

Run from `ROW-Design`. `--solve` is required to reproduce the timing comparison;
without it, the script only reports network sizes.

```powershell
conda run -n row-design-cplex221 python tools\run_5_1_4_network_reduction.py `
  --instances R04 R05 R06 R07 R08 R09 R10 Sioux_Falls_30OD `
  --variants unreduced reduced --solve `
  --mip-gap 0.01 --time-limit 7200 --master-time-limit 600 --max-iter 500 `
  --max-scenario-workers 4 --solver-threads 1 --parallel-scenarios `
  --out results\reproduced\section5_1_4_network_reduction
```

Current aggregate rows: 16.
Timing comparison included: yes.

Main table fields:

| Paper item | CSV column |
|---|---|
| Nodes before/after reduction | `time_space_nodes` by `variant` |
| Arcs before/after reduction | `time_space_arcs` and `time_space_travel_arcs` by `variant` |
| Candidate cells | `candidate_cells` |
| Variable-count proxy | `deterministic_equivalent_variables` |
| Solution time | `solution_time_seconds` |
| Final gap | `reported_gap` |

## Data Notes

`aggregate.csv` has 16 rows, covering 8 networks under both `unreduced` and `reduced` variants. Required size and reduction fields are present, including candidate cells, deterministic-equivalent variables, time-space nodes/arcs, R1/R2/R3 before-after counts, solve time, gap, and termination status. All run-level directories include `summary.json`, `progress.csv`, `progress.json`, `row_schedule_incumbent.csv`, `audit.txt`, and `reduction.json`.
