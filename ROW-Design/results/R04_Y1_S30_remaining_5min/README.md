# R04_Y1, S30 — five-minute strategy comparison

Each Benders strategy was allowed 300 seconds of algorithm time with a 1% master-MIP target and identical preprocessing, parallel-scenario, thread, root-LP, and warm-start settings.

`comparison_algorithm_5min.csv` records the terminal `progress.json` values at the algorithm time limit.  `row_schedule_incumbent.csv`, `progress.csv`, and `benders_cuts.json` in each strategy folder are the corresponding incumbent solution and convergence records.

The post-limit full cut audit was intentionally interrupted for cut-set and Pareto so that the next requested strategy could start immediately.  Complete scenario-allocation, capacity-residual, and diagnostic reports were subsequently reconstructed from each saved incumbent by `tools/report_saved_incumbent.py`; the recomputed objective agrees with the recorded UB for all three strategies.  `summary.json` is absent because each original CLI run was interrupted after its algorithm time limit, before it could perform that full cut audit.
