from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path

from row.benders import solve_benders
from row.data import Data, load_excel
from row.extensive_form import solve_extensive
from row.network import build_network
from row.reduction import reduce_network
from row.subproblem import Recourse
from row.validation import cut_audit


METHODS = ("BD", "BD-P", "BD-NR", "BD-P-NR")


def toy_instance() -> Data:
    arcs = {
        1: {
            "arc_id": 1,
            "tail": 1,
            "head": 2,
            "ROW_candidate": 1,
            "autonomous_travel_periods": 1,
            "conventional_travel_periods": 1,
            "autonomous_unit_cost": 1.0,
            "conventional_unit_cost": 2.0,
            "emergency_unit_cost": 100.0,
            "ROW_resource_weight": 1.0,
            "ROW_activation_cost_per_period": 3.0,
            "base_capacity_per_period": 10.0,
        }
    }
    periods = [1, 2, 3, 4]
    commodities = {
        1: {
            "commodity_id": 1,
            "origin": 1,
            "destination": 2,
            "release_period": 1,
            "deadline_period": 4,
            "emergency_unit_cost": 100.0,
        }
    }
    cap = {(1, 1, t): (10.0, 10.0) for t in periods}
    return Data(
        Path("toy.xlsx"),
        {"resource_budget": 10.0, "ROW_capacity_share": 0.1},
        [1, 2],
        arcs,
        commodities,
        periods,
        {1: {"scenario_id": 1}},
        {(1, 1): 5.0},
        cap,
        [(1, 1), (1, 2), (1, 3)],
        {"S10": {1: 1.0}, "S20": {}, "S30": {}},
    )


def selected_cells(y: dict[tuple[int, int], float]) -> str:
    return json.dumps([list(cell) for cell, value in y.items() if value > 0.5])


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def add_row(rows: list[dict], case: str, method: str, result: dict, reference: float, tol: float) -> None:
    rows.append(
        {
            "case": case,
            "method": method,
            "objective": result["objective"],
            "reference_objective": reference,
            "abs_diff": abs(result["objective"] - reference),
            "pass": close(result["objective"], reference, tol) and result.get("gap", 0.0) <= tol,
            "LB": result.get("LB"),
            "UB": result.get("UB"),
            "gap": result.get("gap"),
            "iterations": result.get("iterations"),
            "seconds": result.get("seconds"),
            "cuts": result.get("cuts", 0),
            "exact_benders_cuts": result.get("exact_benders_cuts", 0),
            "pareto_cuts": result.get("pareto_cuts", 0),
            "nr_cuts": result.get("nr_cuts", 0),
            "selected_cells": selected_cells(result.get("y", {})),
        }
    )


def run_toy(rows: list[dict], tol: float) -> dict:
    d = toy_instance()
    n = build_network(d)
    enumerated = min(
        3.0 * sum(bits) + Recourse(d, n, 1).solve(dict(zip(d.candidates, bits)))["value"]
        for bits in itertools.product((0.0, 1.0), repeat=len(d.candidates))
    )
    rows.append(
        {
            "case": "toy_three_binary",
            "method": "enumeration",
            "objective": enumerated,
            "reference_objective": enumerated,
            "abs_diff": 0.0,
            "pass": True,
            "LB": enumerated,
            "UB": enumerated,
            "gap": 0.0,
            "iterations": 1,
            "seconds": None,
            "cuts": 0,
            "exact_benders_cuts": 0,
            "pareto_cuts": 0,
            "nr_cuts": 0,
            "selected_cells": "",
        }
    )
    ef = solve_extensive(d, n, {1: 1.0}, gap=tol)
    add_row(rows, "toy_three_binary", "extensive_form", ef, enumerated, tol)
    for mode in METHODS:
        bd = solve_benders(d, n, {1: 1.0}, mode=mode, gap=tol, max_iter=30)
        failures = cut_audit(d, n, {1: 1.0}, bd["cut_records"])
        failures += cut_audit(d, n, {1: 1.0}, bd["nr_cut_records"], relaxation=True)
        if failures:
            raise RuntimeError(f"toy cut audit failed for {mode}: {failures[:3]}")
        add_row(rows, "toy_three_binary", mode, bd, enumerated, tol)
    return {"reference_objective": enumerated, "candidate_count": len(d.candidates)}


def run_r04(rows: list[dict], args: argparse.Namespace, tol: float) -> dict:
    d = load_excel(args.excel, args.instance)
    n = build_network(d)
    n, reduction_stats = reduce_network(d, n)
    original_candidate_count = len(d.candidates)
    d.candidates = d.candidates[: args.candidate_count]
    scenarios = {args.scenario: 1.0}
    ef = solve_extensive(
        d,
        n,
        scenarios,
        gap=tol,
        time_limit=args.time_limit,
        solver_threads=args.solver_threads,
    )
    reference = ef["objective"]
    add_row(rows, "r04_reduced_single_scenario", "extensive_form", ef, reference, tol)
    for mode in METHODS:
        bd = solve_benders(
            d,
            n,
            scenarios,
            mode=mode,
            gap=tol,
            max_iter=args.max_iter,
            time_limit=args.time_limit,
            master_time_limit=args.master_time_limit,
            solver_threads=args.solver_threads,
        )
        add_row(rows, "r04_reduced_single_scenario", mode, bd, reference, tol)
    return {
        "instance": d.instance_id,
        "scenario": args.scenario,
        "original_candidate_count": original_candidate_count,
        "tested_candidate_count": len(d.candidates),
        "reduction_stats": reduction_stats,
        "reference_objective": reference,
    }


def write_outputs(out: Path, rows: list[dict], meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=2), encoding="utf8")
    with (out / "comparison.csv").open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    passed = sum(1 for row in rows if row["pass"])
    lines = [
        "# 5.1.1 Correctness Check",
        "",
        f"Rows passed: {passed}/{len(rows)}",
        "",
        "## Cases",
        "",
        f"- Toy three-binary enumeration reference: {meta['toy']['reference_objective']:.10f}",
        (
            "- R04 reduced single-scenario reference: "
            f"{meta['r04']['reference_objective']:.10f}; "
            f"instance={meta['r04']['instance']}; "
            f"scenario={meta['r04']['scenario']}; "
            f"candidate_count={meta['r04']['tested_candidate_count']}/"
            f"{meta['r04']['original_candidate_count']}"
        ),
        "",
        "## Results",
        "",
        "| Case | Method | Objective | Abs diff | Gap | Iterations | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {method} | {objective:.10f} | {abs_diff:.3g} | {gap:.3g} | {iterations} | {pass} |".format(
                **row
            )
        )
    (out / "correctness_report.md").write_text("\n".join(lines) + "\n", encoding="utf8")


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    default_excel = repo / "\u6570\u636e" / "R04_ROW_H1_M10.xlsx"
    parser = argparse.ArgumentParser(description="Run Section 5.1.1 correctness checks.")
    parser.add_argument("--excel", type=Path, default=default_excel)
    parser.add_argument("--instance", default="R04_Y1_S10_H1_M10")
    parser.add_argument("--scenario", type=int, default=1)
    parser.add_argument("--candidate-count", type=int, default=6)
    parser.add_argument("--tol", type=float, default=1e-6)
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--master-time-limit", type=float, default=60.0)
    parser.add_argument("--max-iter", type=int, default=50)
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("results") / "section5_1_1_correctness")
    args = parser.parse_args()
    rows: list[dict] = []
    meta = {"toy": run_toy(rows, args.tol), "r04": run_r04(rows, args, args.tol)}
    write_outputs(args.out, rows, meta)
    if not all(row["pass"] for row in rows):
        raise SystemExit("correctness check failed")
    print(json.dumps({"out": str(args.out), "rows": len(rows), "passed": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
