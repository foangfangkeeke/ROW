from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cplex

from row.benders import _master
from row.pareto import select_pareto_cut
from row.subproblem import Recourse
from row.validation import cut_audit

from section5_2_common import (
    METHOD,
    add_instance_arguments,
    design_context,
    evaluate_schedule,
    load_base_instance,
    load_schedule,
    upsert_aggregate,
    write_base_metadata,
    write_json,
    write_policy_outputs,
    write_schedule,
)


def expand_static(arcs: list[int], cells_by_arc: dict[int, list[tuple[int, int]]], x: dict[int, float]) -> dict[tuple[int, int], float]:
    y = {}
    for a in arcs:
        for cell in cells_by_arc[a]:
            y[cell] = x[a]
    return y


def aggregate_beta(arcs: list[int], beta: dict[tuple[int, int], float]) -> dict[int, float]:
    out = {a: 0.0 for a in arcs}
    for (a, _), value in beta.items():
        if a in out:
            out[a] += value
    return out


def add_static_cut(model, theta_index, x_index, scenario, alpha, beta_by_arc, name):
    indices = [theta_index[scenario]]
    values = [1.0]
    for a, value in beta_by_arc.items():
        if abs(value) > 1e-12:
            indices.append(x_index[a])
            values.append(-value)
    model.linear_constraints.add(
        lin_expr=[cplex.SparsePair(indices, values)],
        senses=["G"],
        rhs=[alpha],
        names=[name],
    )


def checkpoint(path: Path, row: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / "progress.json", row)
    exists = (path / "progress.csv").exists()
    with (path / "progress.csv").open("a", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def solve_static_benders(d, n, probabilities, args, output_dir: Path) -> dict:
    cells_by_arc: dict[int, list[tuple[int, int]]] = {}
    for cell in d.candidates:
        cells_by_arc.setdefault(cell[0], []).append(cell)
    arcs = sorted(cells_by_arc)
    cost_by_arc = {a: sum(d.activation_cost(cell) for cell in cells_by_arc[a]) for a in arcs}
    resource_by_arc = {a: sum(d.resource(cell) for cell in cells_by_arc[a]) for a in arcs}

    started = time.time()
    x_names = [f"x_{a}" for a in arcs]
    theta_names = [f"theta_{s}" for s in probabilities]
    names = x_names + theta_names
    x_index = {a: i for i, a in enumerate(arcs)}
    theta_index = {s: len(arcs) + i for i, s in enumerate(probabilities)}

    model = cplex.Cplex()
    for setter in (model.set_log_stream, model.set_results_stream, model.set_warning_stream, model.set_error_stream):
        setter(None)
    model.objective.set_sense(model.objective.sense.minimize)
    model.variables.add(
        names=x_names,
        obj=[cost_by_arc[a] for a in arcs],
        types=["B"] * len(arcs),
        lb=[0.0] * len(arcs),
        ub=[1.0] * len(arcs),
    )
    model.variables.add(names=theta_names, obj=[probabilities[s] for s in probabilities], lb=[0.0] * len(theta_names))
    model.linear_constraints.add(
        lin_expr=[cplex.SparsePair(list(range(len(arcs))), [resource_by_arc[a] for a in arcs])],
        senses=["L"],
        rhs=[float(d.params["resource_budget"])],
        names=["static_row_budget"],
    )

    timing = {"master": 0.0, "exact_recourse": 0.0, "pareto_auxiliary": 0.0, "nr_relaxation": 0.0, "root_nr_generation": 0.0}
    exact_records = []
    nr_records = []
    ordinary = pareto = fallback = aux = 0

    def solve_many(y, relaxation=False):
        tick = time.time()
        reports = [(s, Recourse(d, n, s).solve(y, solver_threads=args.solver_threads, commodity_separable=relaxation)) for s in probabilities]
        timing["nr_relaxation" if relaxation else "exact_recourse"] += time.time() - tick
        return reports

    def solve_master(limit):
        tick = time.time()
        obj, bound, values = _master(model, names, args.mip_gap, limit, args.solver_threads)
        timing["master"] += time.time() - tick
        x = dict(zip(arcs, values[: len(arcs)]))
        return obj, bound, values, x, expand_static(arcs, cells_by_arc, x)

    def add_nr(y, label, lower=None):
        added = 0
        for s, report in solve_many(y, relaxation=True):
            alpha, beta = report["alpha"], report["beta"]
            rhs = alpha + sum(beta.get(cell, 0.0) * y[cell] for cell in y)
            if abs(rhs - report["value"]) > 1e-5:
                raise RuntimeError(f"static NR cut not tight at reference point: scenario={s}, residual={rhs - report['value']}")
            if lower is not None and rhs <= lower[s] + args.nr_violation_tolerance:
                continue
            add_static_cut(model, theta_index, x_index, s, alpha, aggregate_beta(arcs, beta), f"nr_{label}_{s}")
            nr_records.append({"scenario": s, "alpha": alpha, "beta": beta, "reference_y": y.copy(), "value": report["value"], "type": "network_relaxation"})
            added += 1
        return added

    root_before = root_after = None
    tick = time.time()
    _, root_before, _, _, _ = solve_master(None)
    zero_y = expand_static(arcs, cells_by_arc, {a: 0.0 for a in arcs})
    add_nr(zero_y, "zero")
    eta = 0.5 * min(1.0, float(d.params["resource_budget"]) / max(1e-12, sum(resource_by_arc.values())))
    core_x = {a: eta for a in arcs}
    core_y = expand_static(arcs, cells_by_arc, core_x)
    add_nr(core_y, "core")
    _, _, values, _, preliminary_y = solve_master(None)
    lower = {s: values[theta_index[s]] for s in probabilities}
    add_nr(preliminary_y, "preliminary", lower)
    _, root_after, _, _, _ = solve_master(None)
    timing["root_nr_generation"] = time.time() - tick

    ub = float("inf")
    lb = -float("inf")
    incumbent_x = None
    incumbent_y = None
    stopped = False
    it = 0
    for it in range(1, args.max_iter + 1):
        remaining = args.time_limit - (time.time() - started)
        if remaining <= 0:
            stopped = True
            break
        limit = min(remaining, args.master_time_limit)
        _, bound, values, x, y = solve_master(limit)
        lb = max(lb, bound)
        solved = solve_many(y, relaxation=False)
        qsum = sum(probabilities[s] * report["value"] for s, report in solved)
        violated = 0
        for s, report in solved:
            alpha, beta, kind = report["alpha"], report["beta"], "ordinary"
            aux += 1
            tick = time.time()
            try:
                alpha, beta = select_pareto_cut(report, y, core_y)
                kind = "pareto"
                pareto += 1
            except Exception:
                fallback += 1
            timing["pareto_auxiliary"] += time.time() - tick
            rhs = alpha + sum(beta.get(cell, 0.0) * y[cell] for cell in y)
            if abs(rhs - report["value"]) > 1e-5:
                raise RuntimeError(f"static exact cut not tight: scenario={s}, iteration={it}, residual={rhs - report['value']}")
            if values[theta_index[s]] < report["value"] - 1e-6:
                add_static_cut(model, theta_index, x_index, s, alpha, aggregate_beta(arcs, beta), f"exact_{it}_{s}")
                exact_records.append({"scenario": s, "iteration": it, "alpha": alpha, "beta": beta, "reference_y": y.copy(), "value": report["value"], "type": kind})
                violated += 1
                if kind == "ordinary":
                    ordinary += 1
        first = sum(cost_by_arc[a] * x[a] for a in arcs)
        candidate = first + qsum
        if candidate < ub:
            ub = candidate
            incumbent_x = x.copy()
            incumbent_y = y.copy()
        checkpoint(
            output_dir,
            {
                "iteration": it,
                "UB": ub,
                "LB": lb,
                "gap": (ub - lb) / max(1.0, abs(ub)),
                "exact_benders_cuts": len(exact_records),
                "nr_cuts": len(nr_records),
                "elapsed_seconds": time.time() - started,
                "status": "running",
            },
        )
        if not violated or ub - lb <= args.mip_gap * max(1.0, abs(ub)):
            break
        core_x = {a: 0.7 * core_x[a] + 0.3 * x[a] for a in arcs}
        core_y = expand_static(arcs, cells_by_arc, core_x)

    if incumbent_y is None:
        raise RuntimeError("static ROW Benders did not find an incumbent")
    status = "time_limit" if stopped else ("converged" if ub - lb <= args.mip_gap * max(1.0, abs(ub)) else "iteration_limit")
    checkpoint(
        output_dir,
        {
            "iteration": it,
            "UB": ub,
            "LB": lb,
            "gap": (ub - lb) / max(1.0, abs(ub)),
            "exact_benders_cuts": len(exact_records),
            "nr_cuts": len(nr_records),
            "elapsed_seconds": time.time() - started,
            "status": status,
        },
    )
    write_schedule(output_dir / "row_schedule_incumbent.csv", incumbent_y)
    return {
        "method": "static-row-BD-P-NR",
        "objective": ub,
        "LB": lb,
        "UB": ub,
        "gap": (ub - lb) / max(1.0, abs(ub)),
        "iterations": it,
        "cuts": len(exact_records) + len(nr_records),
        "exact_benders_cuts": len(exact_records),
        "nr_cuts": len(nr_records),
        "ordinary_cuts": ordinary,
        "pareto_cuts": pareto,
        "fallback_cuts": fallback,
        "pareto_auxiliary_lps": aux,
        "initial_master_bound_before_nr": root_before,
        "root_bound_after_nr": root_after,
        "root_bound_improvement": None if root_before is None else root_after - root_before,
        "timing_seconds": timing,
        "seconds": time.time() - started,
        "stopped_by_time_limit": stopped,
        "termination_reason": status,
        "parallel_scenarios": False,
        "scenario_workers": 1,
        "solver_threads_per_model": args.solver_threads,
        "y": incumbent_y,
        "cut_records": exact_records,
        "nr_cut_records": nr_records,
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.2 static ROW policy.")
    add_instance_arguments(parser)
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_2_row_value")
    parser.add_argument("--mip-gap", type=float, default=0.01)
    parser.add_argument("--time-limit", type=float, default=7200.0)
    parser.add_argument("--master-time-limit", type=float, default=600.0)
    parser.add_argument("--max-iter", type=int, default=500)
    parser.add_argument("--max-scenario-workers", type=int, default=4)
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--nr-violation-tolerance", type=float, default=1e-6)
    parser.add_argument("--parallel-scenarios", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--audit-cuts", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[1/1] static_row: physical-arc variables, evaluated on {args.network}/{args.demand_level}/{args.scenario_set}")
        return

    d, n, reduction_stats = load_base_instance(repo_root, args.network, args.demand_level, args.scenario_set)
    write_base_metadata(args.out, d, reduction_stats)
    policy_out = args.out / "static_row"
    policy_out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    print("[1/1] START static_row", flush=True)
    summary_path = policy_out / "design_summary.json"
    schedule_path = policy_out / "row_schedule_incumbent.csv"
    if summary_path.exists() and schedule_path.exists() and not args.force:
        design_summary = json.loads(summary_path.read_text(encoding="utf8"))
        y = load_schedule(schedule_path, d.candidates)
    else:
        result = solve_static_benders(d, n, d.probabilities[args.scenario_set], args, policy_out)
        if args.audit_cuts:
            failures = cut_audit(d, n, d.probabilities[args.scenario_set], result["cut_records"])
            failures += cut_audit(d, n, d.probabilities[args.scenario_set], result["nr_cut_records"], relaxation=True)
            if failures:
                raise RuntimeError(f"cut audit failed for static_row: {failures[:3]}")
        y = result["y"]
        design_summary = {
            k: v
            for k, v in result.items()
            if k not in ("y", "cut_records", "nr_cut_records")
        }
        design_summary.update(design_context(d, args.network, args.demand_level, args.scenario_set))
        design_summary.update({"policy": "static_row", "design_scenario_set": args.scenario_set})
        write_json(summary_path, design_summary)
    evaluation = evaluate_schedule(
        d,
        n,
        d.probabilities[args.scenario_set],
        y,
        parallel_scenarios=args.parallel_scenarios,
        max_scenario_workers=args.max_scenario_workers,
        solver_threads=args.solver_threads,
    )
    row = write_policy_outputs(policy_out, y, design_summary, evaluation)
    upsert_aggregate(args.out, row)
    print(
        "[1/1] DONE static_row: objective={:.3f} gap={} elapsed_s={:.1f}".format(
            row["objective"],
            "" if row["design_gap"] is None else f"{row['design_gap']:.6f}",
            time.time() - started,
        ),
        flush=True,
    )
    print(json.dumps({"out": str(args.out), "policy": "static_row"}, indent=2))


if __name__ == "__main__":
    main()
