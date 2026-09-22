from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path

from row.benders import solve_benders
from row.config import ReductionOptions
from row.data import audit_report, load_excel
from row.network import Network, build_network
from row.reduction import reduce_network
from row.validation import cut_audit


METHOD = "BD-P-NR"
NETWORKS = ("R04", "R05", "R06", "R07", "R08", "R09", "R10", "Sioux_Falls_30OD")
SCENARIO_SET = "S10"
DEMAND_LEVEL = "Y1"


@dataclass(frozen=True)
class InstanceSpec:
    network: str
    workbook: Path
    instance_id: str


@dataclass(frozen=True)
class VariantSpec:
    name: str
    reductions: ReductionOptions


VARIANTS = {
    "reduced": VariantSpec("reduced", ReductionOptions(True, True, True)),
    "unreduced": VariantSpec("unreduced", ReductionOptions(False, False, False)),
}


def default_specs(repo_root: Path) -> dict[str, InstanceSpec]:
    data = repo_root / "数据"
    return {
        network: InstanceSpec(
            network=network,
            workbook=data / f"{network}_ROW_H1_M10.xlsx",
            instance_id=f"{network}_{DEMAND_LEVEL}_{SCENARIO_SET}_H1_M10",
        )
        for network in NETWORKS
    }


def count_network(n: Network) -> dict[str, int]:
    time_space_arcs = sum(len(arcs) for arcs in n.arcs.values())
    travel_arcs = sum(1 for arcs in n.arcs.values() for arc in arcs if arc.physical is not None)
    time_space_nodes = sum(len(nodes) for nodes in n.nodes.values())
    return {
        "time_space_nodes": time_space_nodes,
        "time_space_arcs": time_space_arcs,
        "time_space_travel_arcs": travel_arcs,
    }


def flatten_reduction_stats(stats: dict) -> dict:
    row = {}
    for rule in ("R1_shortest_time", "R2_reachability", "R3_budget_paths"):
        item = stats[rule]
        row[f"{rule}_enabled"] = item["enabled"]
        row[f"{rule}_arcs_before"] = item["arcs_before"]
        row[f"{rule}_arcs_after"] = item["arcs_after"]
        row[f"{rule}_arcs_removed"] = item["arcs_before"] - item["arcs_after"]
        row[f"{rule}_arc_reduction_percent"] = (
            None
            if item["arcs_before"] == 0
            else 100.0 * (item["arcs_before"] - item["arcs_after"]) / item["arcs_before"]
        )
    return row


def flatten_summary(summary: dict | None) -> dict:
    if summary is None:
        return {
            "objective": None,
            "UB": None,
            "LB": None,
            "reported_gap": None,
            "solution_time_seconds": None,
            "benders_iterations": None,
            "termination_reason": None,
            "stopped_by_time_limit": None,
        }
    signed_gap = summary.get("gap")
    return {
        "objective": summary.get("objective"),
        "UB": summary.get("UB"),
        "LB": summary.get("LB"),
        "reported_gap": None if signed_gap is None else max(0.0, float(signed_gap)),
        "solution_time_seconds": summary.get("seconds"),
        "benders_iterations": summary.get("iterations"),
        "termination_reason": summary.get("termination_reason"),
        "stopped_by_time_limit": summary.get("stopped_by_time_limit"),
    }


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_markdown(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Section 5.1.4 Network Reduction",
        "",
        "| Network | Variant | Nodes | Arcs | Travel arcs | Candidate cells | DE vars S10 | Time s | Gap | Status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {network} | {variant} | {nodes} | {arcs} | {travel} | {cells} | {de_vars} | {time} | {gap} | {status} |".format(
                network=row["network"],
                variant=row["variant"],
                nodes=row["time_space_nodes"],
                arcs=row["time_space_arcs"],
                travel=row["time_space_travel_arcs"],
                cells=row["candidate_cells"],
                de_vars=row["deterministic_equivalent_variables"],
                time=fmt(row["solution_time_seconds"]),
                gap=fmt(row["reported_gap"], 6),
                status=fmt(row["termination_reason"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def write_readme(path: Path, rows: list[dict], solved: bool) -> None:
    lines = [
        "# 5.1.4 Network Reduction Results",
        "",
        "This directory is produced by `tools/run_5_1_4_network_reduction.py`.",
        "",
        "Default experiment design:",
        "",
        "- Instances: R04-R10 and Sioux_Falls_30OD, Y1/S10.",
        "- Variants: unreduced and R1-R3 reduced networks.",
        "- Method for optional timing comparison: BD-P-NR.",
        "",
        f"Current aggregate rows: {len(rows)}.",
        f"Timing comparison included: {'yes' if solved else 'no'}.",
        "",
        "Main table fields:",
        "",
        "| Paper item | CSV column |",
        "|---|---|",
        "| Nodes before/after reduction | `time_space_nodes` by `variant` |",
        "| Arcs before/after reduction | `time_space_arcs` and `time_space_travel_arcs` by `variant` |",
        "| Candidate cells | `candidate_cells` |",
        "| Variable-count proxy | `deterministic_equivalent_variables` |",
        "| Solution time | `solution_time_seconds` |",
        "| Final gap | `reported_gap` |",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def output_dir_for(args: argparse.Namespace, spec: InstanceSpec, variant: VariantSpec) -> Path:
    return args.out / spec.network / variant.name


def run_variant(spec: InstanceSpec, variant: VariantSpec, args: argparse.Namespace) -> dict:
    d = load_excel(spec.workbook, spec.instance_id)
    n = build_network(d, variant.reductions)
    n, reduction_stats = reduce_network(d, n, variant.reductions)
    probabilities = d.probabilities[SCENARIO_SET]
    counts = count_network(n)
    candidate_cells = len(d.candidates)
    recourse_variables_per_scenario = counts["time_space_arcs"] + 3 * len(d.commodities)
    row = {
        "network": spec.network,
        "instance_id": spec.instance_id,
        "scenario_set": SCENARIO_SET,
        "variant": variant.name,
        "method": METHOD,
        "candidate_cells": candidate_cells,
        "scenarios": len(probabilities),
        "commodities": len(d.commodities),
        "master_variables": candidate_cells + len(probabilities),
        "single_scenario_recourse_variables": recourse_variables_per_scenario,
        "deterministic_equivalent_variables": candidate_cells
        + len(probabilities) * recourse_variables_per_scenario,
        **counts,
        **flatten_reduction_stats(reduction_stats),
    }

    variant_out = output_dir_for(args, spec, variant)
    summary = None
    if not args.dry_run:
        variant_out.mkdir(parents=True, exist_ok=True)
        (variant_out / "audit.txt").write_text(audit_report(d), encoding="utf8")
        (variant_out / "reduction.json").write_text(json.dumps(reduction_stats, indent=2), encoding="utf8")
    if args.solve and not args.dry_run:
        summary_path = variant_out / "summary.json"
        if summary_path.exists() and not args.force:
            summary = json.loads(summary_path.read_text(encoding="utf8"))
        else:
            result = solve_benders(
                d,
                n,
                probabilities,
                mode=METHOD,
                gap=args.mip_gap,
                max_iter=args.max_iter,
                time_limit=args.time_limit,
                master_time_limit=args.master_time_limit,
                output_dir=variant_out,
                parallel_scenarios=args.parallel_scenarios,
                max_scenario_workers=args.max_scenario_workers,
                solver_threads=args.solver_threads,
                nr_violation_tolerance=args.nr_violation_tolerance,
            )
            if args.audit_cuts:
                failures = cut_audit(d, n, probabilities, result["cut_records"])
                failures += cut_audit(d, n, probabilities, result["nr_cut_records"], relaxation=True)
                if failures:
                    raise RuntimeError(f"cut audit failed for {spec.network} {variant.name}: {failures[:3]}")
            summary = {
                k: v
                for k, v in result.items()
                if k not in ("y", "cut_records", "nr_cut_records", "scenario_allocations")
            }
            summary.update(
                {
                    "network": spec.network,
                    "instance": spec.instance_id,
                    "scenario_set": SCENARIO_SET,
                    "variant": variant.name,
                    "number_of_scenarios": len(probabilities),
                    "cut_audit": "passed" if args.audit_cuts else "not_requested",
                }
            )
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    row.update(flatten_summary(summary))
    return row


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.1.4 network-reduction experiments.")
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_1_4_network_reduction")
    parser.add_argument("--instances", nargs="+", default=list(NETWORKS), choices=list(NETWORKS))
    parser.add_argument("--variants", nargs="+", default=["unreduced", "reduced"], choices=list(VARIANTS))
    parser.add_argument("--solve", action="store_true")
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

    specs = default_specs(repo_root)
    rows: list[dict] = []
    total = len(args.instances) * len(args.variants)
    index = 0
    for name in args.instances:
        for variant_name in args.variants:
            index += 1
            label = f"{name}/{variant_name}"
            started = time.time()
            print(f"[{index}/{total}] START {label}", flush=True)
            row = run_variant(specs[name], VARIANTS[variant_name], args)
            rows.append(row)
            if not args.dry_run:
                write_rows(args.out / "aggregate.csv", rows)
                (args.out / "aggregate.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
                write_markdown(args.out / "report.md", rows)
                write_readme(args.out / "README.md", rows, args.solve)
            print(
                "[{}/{}] DONE {}: nodes={} arcs={} de_vars={} status={} time_s={} gap={} elapsed_s={:.1f}".format(
                    index,
                    total,
                    label,
                    row["time_space_nodes"],
                    row["time_space_arcs"],
                    row["deterministic_equivalent_variables"],
                    fmt(row["termination_reason"]),
                    fmt(row["solution_time_seconds"]),
                    fmt(row["reported_gap"], 6),
                    time.time() - started,
                ),
                flush=True,
            )
    if not args.dry_run:
        write_rows(args.out / "aggregate.csv", rows)
        (args.out / "aggregate.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
        write_markdown(args.out / "report.md", rows)
        write_readme(args.out / "README.md", rows, args.solve)
        print(json.dumps({"out": str(args.out), "runs": len(rows), "solve": args.solve}, indent=2))


if __name__ == "__main__":
    main()
