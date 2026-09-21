# 5.1.3 Algorithm Effectiveness Results

This directory is produced by `tools/run_5_1_3_algorithm_effectiveness.py`.

Default experiment design:

- Method: BD-P-NR.
- R04-R10: Y1/Y3/Y5 crossed with S10/S20/S30, 63 runs.
- Sioux_Falls_30OD: Y1 crossed with S10/S20/S30, 3 runs.
- Total default runs: 66.

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
