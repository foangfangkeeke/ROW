# Paused Ω10 correctness run

Status: manually paused on 2026-09-02. These numbers are **not** a final two-stage stochastic objective, and must not be used as a validated result.

The most recent Benders master MIP (with cuts from completed preceding iterations) had:

| Quantity | Value |
|---|---:|
| incumbent master objective | 24833.2595 |
| current master lower bound | 24826.8520 |
| master relative gap | 0.0258% |
| requested correctness gap | 0.0001% (1e-6) |

The most recently completed master solve before the interruption had an objective of 24820.863771 and completed at the requested 1e-6 master MIP gap. It is only a lower-bound master solution; its associated scenario recourse evaluation was in progress when the run was stopped.

Completed model checks before pause:

- Excel data audit passed, including `Delta <= R_H` over all 21,600 scenario-arc-period tuples.
- Exact forward/backward reachability reduced autonomous/conventional travel arcs from 2,644/2,044 to 571/143.
- Scenario 1 recourse at all-zero ROW solved by CPLEX Python 22.2.0.0 with value 30,815.21968574551; dual-cut tightness residual was zero.

