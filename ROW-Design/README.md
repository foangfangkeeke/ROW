# Nighttime ROW stochastic design

The implementation follows the September 16 paper Section 5. The comparison methods are `BD` (ordinary optimal-dual cuts), `BD-P` (Pareto-oriented exact cuts), and `BD-P-NR` (Pareto cuts plus root-only commodity-separable network-relaxation cuts). Exact recourse is always the joint multicommodity LP; NR is only a lower-bounding relaxation assembled as a block-diagonal LP.

Run one method with:

`$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m row.cli <instance.xlsx> --config configs/default_experiment.json --out results/run_name`

Every run writes data/reduction audits, cut records, scenario diagnostics, capacity residuals, a ROW schedule, and `summary.json`. Cut audits test reference tightness and global validity on random feasible fractional schedules. Emergency service guarantees relatively complete recourse, so no feasibility cuts are used.

The three exact reductions R1–R3 are enabled by default. They screen individual time-space nodes, retain only source-to-sink reachable states, and prune budget-infeasible autonomous arcs. The ROW candidate set is not reduced.
