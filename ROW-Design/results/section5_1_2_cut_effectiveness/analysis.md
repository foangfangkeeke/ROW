# Section 5.1.2 Cut Effectiveness Analysis

## Completion Check

- Total runs: 24.
- Instances: R04-R10 and Sioux_Falls_30OD.
- Methods per instance: BD, BD-P, BD-P-NR.
- Pareto status: all BD-P and BD-P-NR runs are `active`; no Pareto fallback occurred.
- Full result tables: `aggregate.csv`, `aggregate.json`, and `report.md`.

## Main Findings

Pareto cuts materially improve convergence on most R04-R09 instances. Plain BD times out on 7 of 8 instances, while BD-P converges on R04, R06, R07, R08, and R09. BD-P-NR also converges on the same five instances.

NR cuts add a fixed root-stage strengthening cost and generate 30 NR cuts in every BD-P-NR run. On this batch, NR does not uniformly improve total solution time relative to BD-P, although it sometimes improves the final bound. Its value should be discussed as mixed rather than universally dominant.

The largest unresolved cases are R05, R10, and Sioux_Falls_30OD. All three methods hit the 7200-second time limit for Sioux_Falls_30OD and for the stronger methods on R10; the final gaps remain large, especially for Sioux_Falls_30OD.

## Method-Level Summary

| Method | Converged | Time limit | Notes |
|---|---:|---:|---|
| BD | 1 | 7 | Only R04 converged; ordinary cuts are weak for this batch. |
| BD-P | 5 | 3 | Strong improvement over BD; Pareto cuts are active in all runs. |
| BD-P-NR | 5 | 3 | NR cuts are active, but total time is often higher than BD-P due to extra generation cost. |

## Speed Pattern

Approximate BD-to-BD-P speedup for converged or time-limited wall-clock comparisons:

| Instance | BD / BD-P time ratio | Interpretation |
|---|---:|---|
| R04 | 7.99 | BD-P much faster. |
| R05 | 1.00 | Both hit time limit; BD-P has much smaller gap. |
| R06 | 6.83 | BD-P much faster and converges. |
| R07 | 23.63 | BD-P much faster and converges. |
| R08 | 27.18 | BD-P much faster and converges. |
| R09 | 27.19 | BD-P much faster and converges. |
| R10 | 1.00 | Both hit time limit; BD-P improves gap but does not close it. |
| Sioux_Falls_30OD | 0.99 | All methods hit time limit; BD-P improves objective and bound but still has a large gap. |

## Fields Needed for the Paper Table

The following columns in `aggregate.csv` match the requested 5.1.2 outputs:

- `solution_time_seconds`
- `benders_iterations`
- `reported_gap`
- `LB`
- `UB`
- `cut_generation_seconds`
- `pareto_cuts`
- `nr_cuts`

Additional diagnostic columns should be retained while drafting:

- `fallback_cuts`
- `pareto_auxiliary_lps`
- `pareto_status`
- `termination_reason`
