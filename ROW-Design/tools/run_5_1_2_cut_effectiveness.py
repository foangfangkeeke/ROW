from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from row.benders import solve_benders
from row.data import audit_report, load_excel
from row.network import build_network
from row.reduction import reduce_network
from row.validation import cut_audit


METHODS = ("BD", "BD-P", "BD-P-NR")
NETWORKS = ("R04", "R05", "R06", "R07", "R08", "R09", "R10", "Sioux_Falls_30OD")


@dataclass(frozen=True)
class InstanceSpec:
    network: str
    workbook: Path
    instance_id: str


def default_specs(repo_root: Path) -> dict[str, InstanceSpec]:
    data = repo_root / "\u6570\u636e"
    specs = {}
    for name in NETWORKS:
        workbook = data / f"{name}_ROW_H1_M10.xlsx"
        instance = f"{name}_Y1_S10_H1_M10"
        specs[name] = InstanceSpec(name, workbook, instance)
    return specs


def parse_methods(values: Iterable[str]) -> list[str]:
    methods = [v.replace("+", "-") for v in values]
    bad = sorted(set(methods) - set(METHODS))
    if bad:
        raise ValueError(f"unknown methods: {bad}; allowed methods are {METHODS}")
    return methods


def flatten_summary(network: str, instance_id: str, scenario_set: str, method: str, summary: dict) -> dict:
    timing = summary.get("timing_seconds", {})
    pareto_seconds = float(timing.get("pareto_auxiliary", 0.0) or 0.0)
    nr_seconds = float(timing.get("nr_relaxation", 0.0) or 0.0)
    pareto_cuts = int(summary.get("pareto_cuts") or 0)
    fallback_cuts = int(summary.get("fallback_cuts") or 0)
    pareto_auxiliary_lps = int(summary.get("pareto_auxiliary_lps") or 0)
    signed_gap = summary.get("gap")
    reported_gap = None if signed_gap is None else max(0.0, float(signed_gap))
    if method not in ("BD-P", "BD-P-NR"):
        pareto_status = "not_applicable"
    elif pareto_cuts > 0 and fallback_cuts == 0:
        pareto_status = "active"
    elif pareto_cuts > 0 and fallback_cuts > 0:
        pareto_status = "partial_fallback"
    elif pareto_auxiliary_lps > 0 and fallback_cuts > 0:
        pareto_status = "all_fallback"
    else:
        pareto_status = "not_attempted"
    return {
        "network": network,
        "instance_id": instance_id,
        "scenario_set": scenario_set,
        "method": method,
        "objective": summary.get("objective"),
        "UB": summary.get("UB"),
        "LB": summary.get("LB"),
        "signed_gap": signed_gap,
        "reported_gap": reported_gap,
        "solution_time_seconds": summary.get("seconds"),
        "benders_iterations": summary.get("iterations"),
        "cut_generation_seconds": pareto_seconds + nr_seconds,
        "pareto_auxiliary_seconds": pareto_seconds,
        "nr_relaxation_seconds": nr_seconds,
        "root_nr_generation_seconds": timing.get("root_nr_generation"),
        "master_seconds": timing.get("master"),
        "exact_recourse_seconds": timing.get("exact_recourse"),
        "cuts": summary.get("cuts"),
        "exact_benders_cuts": summary.get("exact_benders_cuts"),
        "pareto_cuts": pareto_cuts,
        "nr_cuts": summary.get("nr_cuts"),
        "ordinary_cuts": summary.get("ordinary_cuts"),
        "fallback_cuts": fallback_cuts,
        "pareto_auxiliary_lps": pareto_auxiliary_lps,
        "pareto_status": pareto_status,
        "stopped_by_time_limit": summary.get("stopped_by_time_limit"),
        "termination_reason": summary.get("termination_reason"),
        "parallel_scenarios": summary.get("parallel_scenarios"),
        "scenario_workers": summary.get("scenario_workers"),
        "solver_threads_per_model": summary.get("solver_threads_per_model"),
    }


def write_cut_records(path: Path, result: dict) -> None:
    records = result["cut_records"] + result.get("nr_cut_records", [])
    if not records:
        return
    report = []
    for record in records:
        item = {k: v for k, v in record.items() if k not in ("beta", "reference_y")}
        item["beta"] = [
            {"arc_id": cell[0], "period": cell[1], "coefficient": value}
            for cell, value in record["beta"].items()
        ]
        report.append(item)
    path.write_text(json.dumps(report, indent=2), encoding="utf8")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Section 5.1.2 Cut Effectiveness",
        "",
        "| Network | Method | Time s | Iter | Gap | Signed gap | LB | UB | Cut gen s | Pareto cuts | NR cuts | Fallback cuts | Pareto status | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {network} | {method} | {solution_time_seconds:.3f} | {benders_iterations} | "
            "{reported_gap:.6g} | {signed_gap:.6g} | {LB:.6f} | {UB:.6f} | "
            "{cut_generation_seconds:.3f} | {pareto_cuts} | {nr_cuts} | {fallback_cuts} | "
            "{pareto_status} | {termination_reason} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def load_existing_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


def run_instance(spec: InstanceSpec, methods: list[str], args: argparse.Namespace, rows: list[dict]) -> None:
    instance_out = args.out / spec.network
    instance_out.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        for method in methods:
            print(f"{spec.network}: {method} {spec.workbook} --instance {spec.instance_id}")
        return

    d = load_excel(spec.workbook, spec.instance_id)
    n = build_network(d)
    n, reduction_stats = reduce_network(d, n)
    (instance_out / "audit.txt").write_text(audit_report(d), encoding="utf8")
    (instance_out / "reduction.json").write_text(json.dumps(reduction_stats, indent=2), encoding="utf8")
    probabilities = d.probabilities[args.scenario_set]

    for method in methods:
        method_out = instance_out / method
        method_out.mkdir(parents=True, exist_ok=True)
        summary_path = method_out / "summary.json"
        if summary_path.exists() and not args.force:
            summary = load_existing_summary(summary_path)
        else:
            result = solve_benders(
                d,
                n,
                probabilities,
                mode=method,
                gap=args.mip_gap,
                max_iter=args.max_iter,
                time_limit=args.time_limit,
                master_time_limit=args.master_time_limit,
                output_dir=method_out,
                parallel_scenarios=args.parallel_scenarios,
                max_scenario_workers=args.max_scenario_workers,
                solver_threads=args.solver_threads,
                nr_violation_tolerance=args.nr_violation_tolerance,
            )
            if args.audit_cuts:
                failures = cut_audit(d, n, probabilities, result["cut_records"])
                failures += cut_audit(d, n, probabilities, result["nr_cut_records"], relaxation=True)
                if failures:
                    raise RuntimeError(f"cut audit failed for {spec.network} {method}: {failures[:3]}")
            if args.save_cuts:
                write_cut_records(method_out / "benders_cuts.json", result)
            summary = {
                k: v
                for k, v in result.items()
                if k not in ("y", "cut_records", "nr_cut_records", "scenario_allocations")
            }
            summary.update(
                {
                    "network": spec.network,
                    "instance": spec.instance_id,
                    "scenario_set": args.scenario_set,
                    "number_of_scenarios": len(probabilities),
                    "cut_audit": "passed" if args.audit_cuts else "not_requested",
                }
            )
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
        rows.append(flatten_summary(spec.network, spec.instance_id, args.scenario_set, method, summary))
        write_rows(args.out / "aggregate.csv", rows)
        (args.out / "aggregate.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
        write_markdown(args.out / "report.md", rows)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.1.2 cut-effectiveness experiments.")
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_1_2_cut_effectiveness")
    parser.add_argument("--instances", nargs="+", default=list(NETWORKS), choices=list(NETWORKS))
    parser.add_argument("--methods", nargs="+", default=list(METHODS))
    parser.add_argument("--scenario-set", default="S10")
    parser.add_argument("--mip-gap", type=float, default=0.01)
    parser.add_argument("--time-limit", type=float, default=7200.0)
    parser.add_argument("--master-time-limit", type=float, default=600.0)
    parser.add_argument("--max-iter", type=int, default=500)
    parser.add_argument("--max-scenario-workers", type=int, default=4)
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--nr-violation-tolerance", type=float, default=1e-6)
    parser.add_argument("--parallel-scenarios", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--audit-cuts", action="store_true")
    parser.add_argument("--save-cuts", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    methods = parse_methods(args.methods)
    specs = default_specs(repo_root)
    rows: list[dict] = []
    for name in args.instances:
        run_instance(specs[name], methods, args, rows)
    if not args.dry_run:
        write_rows(args.out / "aggregate.csv", rows)
        (args.out / "aggregate.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
        write_markdown(args.out / "report.md", rows)
        print(json.dumps({"out": str(args.out), "runs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
