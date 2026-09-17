# September 16 paper/data alignment

Reference sources: `夜间物流ROW设计_9_16.pdf` and the workbooks in the September 16 data directory.

## Implemented alignment changes

| Paper requirement | Implementation change |
| --- | --- |
| Six one-hour design blocks and 36 ten-minute operating periods; new workbook IDs end in `_H1_M10`. | The block-workbook loader now recognizes the new IDs, defaults to its S30 row, and reads `capacity10_Y*` fields. |
| Equation (1) permits `tau_A = tau_H` after discretization. | The data audit now rejects only `tau_A > tau_H`. |
| Equations (3)--(4), (15): an autonomous traversal needs every intersected design block. | Autonomous travel arcs are constructed only when every occupied block is in `C`; their existing capacity rows enforce every required activation. |
| R1, equation (22), removes individual time-space nodes outside their earliest/latest shortest-time window. | R1 now screens both endpoints of every travel arc using forward and reverse physical shortest-path labels. |
| R2, equation (23), is repeated after R3. | Forward/backward reachability is applied after budget pruning before virtual dispatch/delivery arcs are created. |
| Section 5.2 has R1--R3 only; `C` and the first-stage feasible set are unchanged. | Removed R4 candidate elimination from preprocessing. Legacy `R4_unused_cells` configuration is retained only for archived JSON compatibility and has no effect. |
| Section 6.2.2 compares BD, BD+P, and BD+P+NR. | The comparison runner now defaults to `BD`, `BD-P`, and `BD-P-NR`. |

## Validation completed

1. All eight September 16 workbooks load successfully. Their default S30 instances have the paper dimensions: R04--R06: 360 ROW binaries; R07: 492; R08--R09: 498; R10: 720; Sioux Falls: 456.
2. On updated `R04_Y1_S10_H1_M10`, using two commodities, two scenarios, and three candidate cells that form autonomous paths, the unreduced deterministic equivalent, R1--R3 reduced deterministic equivalent, and BD-P-NR objectives were respectively `14052.680772431602`, `14052.680772431602`, and `14052.680772431606`. The largest difference was `3.64e-12`; Benders closed its gap.
3. Existing in-memory model tests pass (5 passed; two legacy external-workbook tests are skipped when their old workbook is absent).
4. On updated R10, R1 reduces commodity travel arcs from 93,360 to 13,354; R2 and R3 make no further deletion at the baseline budget. The candidate set remains 720, as required by the paper.

The historical result folders in this repository were produced from earlier data and/or the previous four-rule preprocessing and should not be compared numerically with new-data runs.
