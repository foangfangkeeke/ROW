# R04 Y1 S30, H1/M10 — 9.16-data strategy comparison

Input: `R04_ROW_H1_M10.xlsx`, instance `R04_Y1_S30_H1_M10`. All methods use the revised-paper R1--R3 preprocessing, 30 scenarios, four parallel scenario workers, one solver thread per model, and a requested 600-second algorithm limit with a 0.01% relative-gap target.

| Method | Status | Time (s) | UB | LB | Gap | Iterations |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BD | time limit | 614.98 | 51,655.79 | 48,370.79 | 6.3594% | 42 |
| BD-P | converged | 400.23 | 48,989.36 | 48,985.04 | 0.0088% | 30 |
| BD-P-NR | converged | 418.59 | 48,989.36 | 48,984.68 | 0.0096% | 29 |

`BD` reached the requested 600-second loop limit. Its reported 614.98 seconds includes the final, post-limit incumbent scenario evaluation and report persistence; its terminal loop record is retained in `BD/progress.json`. The two Pareto methods converged before the limit. `comparison.csv` is the machine-readable summary and each method folder contains its progress history, terminal summary, and incumbent schedule.
