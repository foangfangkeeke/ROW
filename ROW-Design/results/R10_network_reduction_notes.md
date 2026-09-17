# R10 network-reduction footprint

Measured by rebuilding the actual R10 package workbook for `R10_Y1_S30`, `R10_Y3_S30`, and `R10_Y5_S30`.  The counts are identical for all three variants; scenario demand values do not change the commodity time-space topology.

| Stage | Travel arcs | All time-space arcs | Nodes | ROW candidate cells |
| --- | ---: | ---: | ---: | ---: |
| None | 68,800 | 69,784 | 15,600 | 360 |
| R1 | 68,800 | 69,784 | 15,600 | 360 |
| R1 + R2 | 14,580 | 15,564 | 4,996 | 360 |
| R1 + R2 + R3 | 14,580 | 15,564 | 4,996 | 360 |
| R1 + R2 + R3 + R4 | 14,580 | 15,564 | 4,996 | 360 |

Thus R2 is responsible for the full effective reduction in the mandated sequence: it removes 54,220 of 68,800 travel arcs (78.81%), 54,220 of 69,784 total arcs (77.70%), and 10,604 of 15,600 nodes (67.97%). R1, R3, and R4 have zero marginal reduction after their predecessors for this R10 topology.

R1's zero is specific to the current implementation. It checks only whether a commodity's source-to-destination shortest travel time exceeds its complete release-to-deadline window; all R10 commodities pass this test (minimum slack: 4 periods for the autonomous layer and 3 for the conventional layer), so it removes no complete commodity network. This is coarser than paper formula (23), which screens individual time-space nodes using their earliest and latest feasible arrival times.

R3 remains nontrivial in isolation: with R1/R2 disabled, it removes 24,691 travel arcs (35.89%). Its deletions are already a subset of R2's temporal-reachability deletions here, explaining its zero incremental effect in the prescribed R1-to-R4 pipeline. R4 removes no candidate variables because every one of the 360 candidate cells protects at least one surviving autonomous travel arc.

## Each rule in isolation

| Enabled rule only | Travel arcs | Reduction | All time-space arcs | Nodes | ROW candidate cells |
| --- | ---: | ---: | ---: | ---: | ---: |
| None | 68,800 | — | 69,784 | 15,600 | 360 |
| R1 | 68,800 | 0.00% | 69,784 | 15,600 | 360 |
| R2 | 14,580 | 78.81% | 15,564 | 4,996 | 360 |
| R3 | 44,109 | 35.89% | 45,093 | 11,325 | 360 |
| R4 | 68,800 | 0.00% | 69,784 | 15,600 | 360 |
