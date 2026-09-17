# Nighttime ROW implementation specification

## Data mapping and time discretization

`Physical_Arcs.tail/head` are physical nodes and directed links; `Time_Periods.period` is the discrete planning horizon. `conventional_travel_periods` and `autonomous_travel_periods` are `tau_H` and `tau_A`. The loader audits `tau_A <= tau_H`. If continuous times are supplied in a future schema, they must be converted by `max(1, ceil(time / period_length))` before building the network.

`Commodities(origin,destination,release_period,deadline_period)` map to `(o_k,q_k,r_k,h_k)`. `ROW_candidate` defines the physical candidate link set and all its period cells. `ROW_resource_weight`, `ROW_activation_cost_per_period`, and `resource_budget` map to `rho`, `g`, and `B`.

`Capacity_Base` joined with `Capacity_Factors` yields `(U_A,R_H)` at `(scenario,arc,period)`; `ROW_capacity_share * base_capacity_per_period` is `Delta`. The loader rejects any `Delta > R_H` and negative costs. `Demand_Scenarios.realized_demand` is `d_k^omega`, and `Scenario_Index.probability_S*` supplies scenario probabilities.

## Network and recourse rows

Each commodity/layer uses stable tuple keys rather than workbook row numbers. Dispatch arcs only leave virtual sources; delivery arcs only enter virtual sinks. No intermediate physical waiting arcs or layer-transfer arcs are created. Every autonomous travel entry `(l,t)` has one capacity row for every occupied period in `I_A(l,t)`. Conventional capacity uses the entry-flow interpretation `F_H <= R_H - Delta*y`.

The recourse RHS metadata records each row as `constant + sum(coefficient[cell] * y[cell])`. CPLEX dual multipliers multiplied by that metadata produce `alpha` and `beta`, rather than reconstructing signs manually. Every Benders cut is checked for tightness at its generating schedule; `validation.cut_audit` checks it at random feasible schedules.

## Algorithms and switches

`configs/default_experiment.json` controls scenario set, gap, time limit, reductions, parallelism, and cuts. `cuts.pareto` selects the Magnanti--Wong dual auxiliary LP restricted to the trial-point optimal dual face. If its LP cannot be solved (for example because an external interactive fallback does not expose a primal model), the implementation records a fallback ordinary cut. `cuts.cutset` adds each commodity's scenario minimum controlled cut `z_A <= sum(U_A*y)`.

R1 screens individual time-space nodes with shortest-time lower and upper windows, R2 performs exact forward/backward reachability (again after R3), and R3 iteratively applies the budget surrogate `sum_{xi in R(e)} rho_xi / nbar_{k,xi}`. The candidate set is retained unchanged, as required by the manuscript. `reduction.json` records each rule's input/output arc count. The master is single-threaded by default; `parallel_scenarios` uses independent models in a thread pool for recourse only, and `solver_threads` controls each CPLEX model (use one when parallelizing scenarios).

## Solver

The Python `cplex` wheel may operate in Community mode on large models. Large LP/MIP solves are therefore written and solved by the locally installed CPLEX Interactive Optimizer 22.2.0.0; CPLEX XML solution names add `#ordinal`, which the solver adapter strips before mapping results back to stable model names. When presolve omits a mode-total variable from its sparse XML solution, it is reconstructed from dispatch flow and the demand split, so scenario A/H/emergency reports remain available.
