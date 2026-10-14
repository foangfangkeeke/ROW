# 5.1.3 Algorithm Effectiveness Results

This directory is produced by `tools/run_5_1_3_algorithm_effectiveness.py`.

Default experiment design:

- Method: BD-P-NR.
- R04-R10: Y1/Y3/Y5 crossed with S10/S20/S30, 63 runs.
- Sioux_Falls_30OD: Y1 crossed with S10/S20/S30, 3 runs.
- Total default runs: 66.

## Reproduction

Run from `ROW-Design`. The separate output path preserves the committed results.

```powershell
conda run -n row-design-cplex221 python tools\run_5_1_3_algorithm_effectiveness.py `
  --instances R04 R05 R06 R07 R08 R09 R10 `
  --demands Y1 Y3 Y5 --scenario-sets S10 S20 S30 `
  --include-sioux --sioux-demands Y1 --sioux-scenario-sets S10 S20 S30 `
  --mip-gap 0.01 --time-limit 7200 --master-time-limit 600 --max-iter 500 `
  --max-scenario-workers 4 --solver-threads 1 --parallel-scenarios `
  --out results\reproduced\section5_1_3_algorithm_effectiveness
```

Current aggregate rows: 66.

Main table fields:

| Paper item | CSV column |
|---|---|
| UB | `UB` |
| LB | `LB` |
| Solution time | `solution_time_seconds` |
| Benders iterations | `benders_iterations` |
| Final gap | `reported_gap` |

Use `report.md` for a quick human-readable table and `aggregate.csv` for paper-table processing.

## Data Notes

`aggregate.csv` has 66 rows. The run grid is complete for the script defaults: R04-R10 cover Y1/Y3/Y5 crossed with S10/S20/S30, and Sioux_Falls_30OD covers Y1 crossed with S10/S20/S30. Required fields are present for bounds, gap, runtime, iterations, cut counts, termination status, and parallel settings. All run-level directories include `summary.json`, `progress.csv`, `progress.json`, `row_schedule_incumbent.csv`, `audit.txt`, and `reduction.json`.
