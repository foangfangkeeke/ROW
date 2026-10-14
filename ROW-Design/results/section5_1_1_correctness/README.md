# Section 5.1.1 Correctness Outputs

This directory contains the correctness check produced by `tools/run_5_1_1_correctness.py`.

## Experiment Design

- Toy case: one-link three-binary instance, checked against full enumeration.
- R04 case: `R04_Y1_S10_H1_M10`, scenario `1`, first `6` candidate ROW cells, checked against the extensive form.
- Methods checked: `extensive_form`, `BD`, `BD-P`, `BD-NR`, and `BD-P-NR`. The toy case also includes the enumeration reference row.

## Reproduction

Run from `ROW-Design`. The separate output path preserves the committed results.

```powershell
conda run -n row-design-cplex221 python tools\run_5_1_1_correctness.py `
  --instance R04_Y1_S10_H1_M10 --scenario 1 --candidate-count 6 `
  --tol 1e-6 --time-limit 120 --master-time-limit 60 --max-iter 50 `
  --solver-threads 1 --out results\reproduced\section5_1_1_correctness
```

## Current Output Status

- `comparison.csv` has 11 rows.
- All 11 rows have `pass=True`.
- `summary.json` stores the same rows plus metadata for the toy and R04 checks.
- `correctness_report.md` is the generated human-readable report.

## Required Fields

`comparison.csv` includes the required correctness and diagnostic fields:

| Item | Column |
|---|---|
| Test case | `case` |
| Method | `method` |
| Objective | `objective` |
| Reference objective | `reference_objective` |
| Absolute difference | `abs_diff` |
| Pass flag | `pass` |
| Bounds | `LB`, `UB` |
| Gap | `gap` |
| Runtime and iterations | `seconds`, `iterations` |
| Cut counts | `cuts`, `exact_benders_cuts`, `pareto_cuts`, `nr_cuts` |
| Selected ROW cells | `selected_cells` |

## Completeness Note

The current outputs are complete for Section 5.1.1. They verify that the Benders variants reproduce the enumeration or extensive-form reference on the two validation cases.
