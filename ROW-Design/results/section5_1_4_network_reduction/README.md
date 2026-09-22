# 5.1.4 Network Reduction Results

This directory is produced by `tools/run_5_1_4_network_reduction.py`.

Default experiment design:

- Instances: R04-R10 and Sioux_Falls_30OD, Y1/S10.
- Variants: unreduced and R1-R3 reduced networks.
- Method for optional timing comparison: BD-P-NR.

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
