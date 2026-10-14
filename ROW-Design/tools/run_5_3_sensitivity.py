from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from row.benders import solve_benders
from row.validation import cut_audit

from section5_2_common import (
    METHOD,
    add_instance_arguments,
    design_context,
    evaluate_schedule,
    load_base_instance,
    load_schedule,
    write_base_metadata,
    write_json,
    write_policy_outputs,
)


BUDGET_RATIOS = [0.15, 0.25, 0.35, 0.45]
BACKGROUND_FACTORS = [0.5, 1.5, 2.0]
DEMAND_FACTORS = [0.5, 1.5, 2.0]


def label_value(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def total_candidate_resource(d) -> float:
    return sum(d.resource(cell) for cell in d.candidates)


def with_budget_ratio(d, ratio: float):
    params = dict(d.params)
    params["resource_budget"] = ratio * total_candidate_resource(d)
    return replace(d, params=params)


def with_demand_factor(d, factor: float):
    demand = {key: value * factor for key, value in d.demand.items()}
    return replace(d, demand=demand)


def with_background_factor(d, factor: float):
    lo, hi = (float(x) for x in str(d.params["background_share_bounds"]).split(","))
    row_share = float(d.params["ROW_capacity_share"])
    cap = {}
    for (s, a, t), (row_capacity, h_capacity) in d.cap.items():
        total = float(d.arcs[a]["base_capacity_per_period"])
        current_share = max(0.0, min(1.0, 1.0 - h_capacity / total))
        scaled_share = min(hi, max(lo, current_share * factor))
        row_cell = d.row_cell(a, t)
        min_h_capacity = row_share * total if row_cell in d.candidates else 0.0
        cap[s, a, t] = (row_capacity, max(min_h_capacity, total * (1.0 - scaled_share)))
    return replace(d, cap=cap)


def sensitivity_cases(d, dimensions: list[str]) -> list[dict[str, Any]]:
    cases = []
    if "budget" in dimensions:
        total = total_candidate_resource(d)
        for value in BUDGET_RATIOS:
            cases.append(
                {
                    "dimension": "budget",
                    "value": value,
                    "case": f"budget_{label_value(value)}",
                    "data": with_budget_ratio(d, value),
                    "description": f"resource_budget={value:g}*total_candidate_resource={value * total:.6f}",
                }
            )
    if "background" in dimensions:
        for value in BACKGROUND_FACTORS:
            cases.append(
                {
                    "dimension": "background",
                    "value": value,
                    "case": f"background_{label_value(value)}",
                    "data": with_background_factor(d, value),
                    "description": f"background traffic factor={value:g}",
                }
            )
    if "demand" in dimensions:
        for value in DEMAND_FACTORS:
            cases.append(
                {
                    "dimension": "demand",
                    "value": value,
                    "case": f"demand_{label_value(value)}",
                    "data": with_demand_factor(d, value),
                    "description": f"demand factor={value:g}",
                }
            )
    return cases


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Section 5.3 Sensitivity Analysis",
        "",
        "| Dimension | Value | Total cost | Fixed | A share | H share | E share | Open arcs | Lane-hours | Budget use | Design s | Gap | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {dimension} | {value:g} | {objective:.3f} | {fixed_cost:.3f} | {A_volume_share:.4f} | {H_volume_share:.4f} | {E_volume_share:.4f} | {open_directed_arcs} | {open_lane_hours} | {weighted_budget_usage:.4f} | {design_time} | {gap} | {status} |".format(
                dimension=row["dimension"],
                value=float(row["sensitivity_value"]),
                objective=row["objective"],
                fixed_cost=row["fixed_cost"],
                A_volume_share=row["A_volume_share"],
                H_volume_share=row["H_volume_share"],
                E_volume_share=row["E_volume_share"],
                open_directed_arcs=row["open_directed_arcs"],
                open_lane_hours=row["open_lane_hours"],
                weighted_budget_usage=row["weighted_budget_usage"],
                design_time="" if row["design_time_seconds"] is None else f"{row['design_time_seconds']:.3f}",
                gap="" if row["design_gap"] is None else f"{row['design_gap']:.6f}",
                status=row["design_status"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def run_case(base_network, base_reduction_stats, case: dict[str, Any], args: argparse.Namespace, context: dict[str, Any]) -> dict[str, Any]:
    d = case["data"]
    n = base_network
    case_out = args.out / case["case"]
    case_out.mkdir(parents=True, exist_ok=True)
    summary_path = case_out / "design_summary.json"
    schedule_path = case_out / "row_schedule_incumbent.csv"

    print(f"START {case['case']}: {case['description']}", flush=True)
    started = time.time()
    if summary_path.exists() and schedule_path.exists() and not args.force:
        design_summary = json.loads(summary_path.read_text(encoding="utf8"))
        y = load_schedule(schedule_path, d.candidates)
    else:
        result = solve_benders(
            d,
            n,
            d.probabilities[args.scenario_set],
            mode=METHOD,
            gap=args.mip_gap,
            max_iter=args.max_iter,
            time_limit=args.time_limit,
            master_time_limit=args.master_time_limit,
            output_dir=case_out,
            parallel_scenarios=args.parallel_scenarios,
            max_scenario_workers=args.max_scenario_workers,
            solver_threads=args.solver_threads,
            nr_violation_tolerance=args.nr_violation_tolerance,
        )
        if args.audit_cuts:
            failures = cut_audit(d, n, d.probabilities[args.scenario_set], result["cut_records"])
            failures += cut_audit(d, n, d.probabilities[args.scenario_set], result["nr_cut_records"], relaxation=True)
            if failures:
                raise RuntimeError(f"cut audit failed for {case['case']}: {failures[:3]}")
        y = result["y"]
        design_summary = {
            k: v
            for k, v in result.items()
            if k not in ("y", "cut_records", "nr_cut_records", "scenario_allocations")
        }
        design_summary.update(context)
        design_summary.update(
            {
                "policy": "stochastic_row",
                "design_scenario_set": args.scenario_set,
                "sensitivity_dimension": case["dimension"],
                "sensitivity_value": case["value"],
                "sensitivity_case": case["case"],
                "sensitivity_description": case["description"],
                "baseline_reduction_stats": base_reduction_stats,
            }
        )
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
    row = write_policy_outputs(case_out, y, design_summary, evaluation)
    row.update(
        {
            "dimension": case["dimension"],
            "sensitivity_value": case["value"],
            "sensitivity_case": case["case"],
            "sensitivity_description": case["description"],
            "elapsed_seconds": time.time() - started,
        }
    )
    print(
        "DONE {case}: objective={objective:.3f} gap={gap} status={status} elapsed_s={elapsed:.1f}".format(
            case=case["case"],
            objective=row["objective"],
            gap="" if row["design_gap"] is None else f"{row['design_gap']:.6f}",
            status=row["design_status"],
            elapsed=row["elapsed_seconds"],
        ),
        flush=True,
    )
    return row


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.3 sensitivity analysis.")
    add_instance_arguments(parser)
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_3_sensitivity")
    parser.add_argument("--dimensions", nargs="+", default=["budget", "background", "demand"], choices=["budget", "background", "demand"])
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

    d, n, reduction_stats = load_base_instance(repo_root, args.network, args.demand_level, args.scenario_set)
    cases = sensitivity_cases(d, args.dimensions)
    if args.dry_run:
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['case']}: {case['description']}")
        return

    write_base_metadata(args.out, d, reduction_stats)
    rows = []
    context = design_context(d, args.network, args.demand_level, args.scenario_set)
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] sensitivity {case['case']}", flush=True)
        rows.append(run_case(n, reduction_stats, case, args, context))
        write_rows(args.out / "aggregate.csv", rows)
        write_json(args.out / "aggregate.json", rows)
        write_report(args.out / "report.md", rows)
    print(json.dumps({"out": str(args.out), "cases": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
