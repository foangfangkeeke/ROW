# R10_Y5 / Omega10 / ordinary Benders — manually stopped

Run configuration: master MIP gap target 1%, total time limit 3,600 seconds, maximum 500 Benders iterations. The run was manually stopped after approximately 463 seconds (22:33:09–22:40:52, 2026-09-02).

## Recoverable final state

| Item | Value |
|---|---:|
| completed master solves | 44 |
| latest completed master objective | 63,093.847314 |
| master MIP gap target | 1% |
| planned total time limit | 3,600 s |
| actual elapsed before stop | about 463 s |

## Important limitation

This prototype did not checkpoint the Benders incumbent and global lower bound during execution. Because the process was stopped before it wrote `summary.json`, the global stochastic-program UB, global LB, global Benders gap, incumbent ROW schedule, and scenario allocations cannot be reconstructed reliably from the CPLEX master log. The master objective above is **not** the stochastic-program objective and must not be reported as one.

Future runs must write a per-iteration checkpoint containing Benders iteration, incumbent UB, global LB, global gap, first-stage cost, expected recourse cost, cuts, and elapsed time.
