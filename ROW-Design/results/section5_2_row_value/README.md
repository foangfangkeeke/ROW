# Section 5.2 ROW Value Outputs

This directory contains the Section 5.2 policy comparison produced by `tools/run_5_2_row_value.py`.

## Experiment Design

- Network: `Sioux_Falls_30OD`.
- Scenario set: `S10`.
- Demand levels in the full run: `Y1`, `Y3`, and `Y5`.
- Policies per demand level: `no_row`, `static_row`, `ave_row`, and `stochastic_row`.
- Default full command:

```powershell
cd C:\faq_work\Papers\ROW\ROW-Design
conda run -n row-design-cplex221 python tools\run_5_2_row_value.py `
  --network Sioux_Falls_30OD --demand-levels Y1 Y3 Y5 --scenario-set S10 `
  --policies no_row static_row ave_row stochastic_row `
  --mip-gap 0.01 --time-limit 7200 --master-time-limit 600 --max-iter 500 `
  --max-scenario-workers 4 --solver-threads 1 --parallel-scenarios `
  --out results\reproduced\section5_2_row_value
```

## Current Output Status

- Formal outputs are under `Y1`, `Y3`, and `Y5`.
- Each demand-level subdirectory has 4 rows in `aggregate.csv`, one per policy.
- Status counts per demand level: 1 `not_optimized` (`no_row`) and 3 `time_limit` design solves.
- All policy directories under `Y1`, `Y3`, and `Y5` contain the expected detailed files.

## Required Fields

Each demand-level `aggregate.csv` includes the fields needed for the Section 5.2 table:

| Item | Column |
|---|---|
| Instance parameters | `network`, `demand_level`, `scenario_set`, `instance_id` |
| Policy | `policy` |
| Total and component costs | `objective`, `fixed_cost`, `expected_recourse_cost`, `A_transport_cost`, `H_transport_cost`, `outsourcing_cost` |
| Mode shares | `A_volume_share`, `H_volume_share`, `E_volume_share` |
| Time metrics | `average_release_to_delivery_periods`, `average_network_transport_periods` |
| ROW opening metrics | `open_directed_arcs`, `open_lane_hours`, `ROW_resource_usage`, `weighted_budget_usage` |
| ROW flow metrics | `row_entering_flow`, `row_entry_capacity`, `row_entry_capacity_utilization` |
| Design solve diagnostics | `design_time_seconds`, `design_iterations`, `design_gap`, `design_status` |

## Detailed Files

Each policy directory contains:

| File | Meaning |
|---|---|
| `design_summary.json` | Design solve metadata and final bounds or status. |
| `evaluation.json` | Policy-level evaluation metrics without bulky scenario/link tables. |
| `scenario_reports.json` | Scenario-level recourse cost and A/H/E commodity allocation. |
| `expected_link_metrics.csv` | One row per physical link, averaged over scenarios. |
| `scenario_link_metrics.csv` | One row per scenario and physical link. |
| `scenario_arc_period_metrics.csv` | One row per scenario, physical link, and period. |
| `row_schedule.csv` | Open ROW cells for the evaluated policy. |

## Reading Notes

The blank `row_entry_capacity_utilization` and `design_gap` cells in each demand-level table occur on the `no_row` policy. That policy has no ROW capacity and is not optimized, so those values are not applicable rather than missing.

All `static_row`, `ave_row`, and `stochastic_row` design runs ended at the time
limit, with final gaps between 0.4064 and 0.8092. Their reported objectives are
evaluations of the saved feasible incumbents under a common computational
budget. They do not establish an optimal policy ranking or a conclusive value
of stochastic optimization.
