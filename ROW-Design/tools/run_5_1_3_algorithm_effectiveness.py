from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from row.benders import solve_benders
from row.data import audit_report, load_excel
from row.network import build_network
from row.reduction import reduce_network
from row.validation import cut_audit


METHOD = "BD-P-NR"
NETWORKS = ("R04", "R05", "R06", "R07", "R08", "R09", "R10")
SIOUX_NETWORK = "Sioux_Falls_30OD"
ALL_NETWORKS = NETWORKS + (SIOUX_NETWORK,)
DEMAND_LEVELS = ("Y1", "Y3", "Y5")
SCENARIO_SETS = ("S10", "S20", "S30")


@dataclass(frozen=True)
class ExperimentSpec:
    network: str
    demand_level: str
    scenario_set: str
    workbook: Path
    instance_id: str


def build_specs(args: argparse.Namespace, repo_root: Path) -> list[ExperimentSpec]:
    data = repo_root / "数据"
    specs: list[ExperimentSpec] = []

    for network in args.instances:
        workbook = data / f"{network}_ROW_H1_M10.xlsx"
        for demand in args.demands:
            for scenario_set in args.scenario_sets:
                specs.append(
                    ExperimentSpec(
                        network=network,
                        demand_level=demand,
                        scenario_set=scenario_set,
                        workbook=workbook,
                        instance_id=f"{network}_{demand}_{scenario_set}_H1_M10",
                    )
                )

    if args.include_sioux:
        workbook = data / f"{SIOUX_NETWORK}_ROW_H1_M10.xlsx"
        for demand in args.sioux_demands:
            for scenario_set in args.sioux_scenario_sets:
                specs.append(
                    ExperimentSpec(
                        network=SIOUX_NETWORK,
                        demand_level=demand,
                        scenario_set=scenario_set,
                        workbook=workbook,
                        instance_id=f"{SIOUX_NETWORK}_{demand}_{scenario_set}_H1_M10",
                    )
                )
    return specs


def parse_subset(values: Iterable[str], allowed: tuple[str, ...], label: str) -> list[str]:
    bad = sorted(set(values) - set(allowed))
    if bad:
        raise ValueError(f"unknown {label}: {bad}; allowed values are {allowed}")
    return list(values)


def flatten_summary(spec: ExperimentSpec, summary: dict) -> dict:
    timing = summary.get("timing_seconds", {})
    pareto_seconds = float(timing.get("pareto_auxiliary", 0.0) or 0.0)
    nr_seconds = float(timing.get("nr_relaxation", 0.0) or 0.0)
    signed_gap = summary.get("gap")
    reported_gap = None if signed_gap is None else max(0.0, float(signed_gap))
    return {
        "network": spec.network,
        "demand_level": spec.demand_level,
        "scenario_set": spec.scenario_set,
        "instance_id": spec.instance_id,
        "method": METHOD,
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
        "pareto_cuts": summary.get("pareto_cuts"),
        "nr_cuts": summary.get("nr_cuts"),
        "ordinary_cuts": summary.get("ordinary_cuts"),
        "fallback_cuts": summary.get("fallback_cuts"),
        "pareto_auxiliary_lps": summary.get("pareto_auxiliary_lps"),
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


def fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_markdown(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Section 5.1.3 Algorithm Effectiveness",
        "",
        "| Network | Demand | Scenarios | Time s | Iter | Gap | Signed gap | LB | UB | Pareto cuts | NR cuts | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {network} | {demand_level} | {scenario_set} | {time} | {iters} | "
            "{gap} | {signed_gap} | {lb} | {ub} | {pareto_cuts} | {nr_cuts} | {status} |".format(
                network=row["network"],
                demand_level=row["demand_level"],
                scenario_set=row["scenario_set"],
                time=fmt(row["solution_time_seconds"]),
                iters=fmt(row["benders_iterations"], 0),
                gap=fmt(row["reported_gap"], 6),
                signed_gap=fmt(row["signed_gap"], 6),
                lb=fmt(row["LB"], 6),
                ub=fmt(row["UB"], 6),
                pareto_cuts=fmt(row["pareto_cuts"], 0),
                nr_cuts=fmt(row["nr_cuts"], 0),
                status=row["termination_reason"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def load_existing_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


def output_dir_for(args: argparse.Namespace, spec: ExperimentSpec) -> Path:
    return args.out / spec.network / spec.demand_level / spec.scenario_set


def run_spec(spec: ExperimentSpec, args: argparse.Namespace, rows: list[dict], index: int, total: int) -> None:
    label = f"{spec.network}/{spec.demand_level}/{spec.scenario_set}"
    if args.dry_run:
        print(f"[{index}/{total}] {label}: {METHOD} {spec.workbook} --instance {spec.instance_id} --scenario-set {spec.scenario_set}")
        return

    started = time.time()
    spec_out = output_dir_for(args, spec)
    spec_out.mkdir(parents=True, exist_ok=True)
    summary_path = spec_out / "summary.json"
    if summary_path.exists() and not args.force:
        print(f"[{index}/{total}] REUSE {label}: {spec.instance_id}", flush=True)
        summary = load_existing_summary(summary_path)
    else:
        print(f"[{index}/{total}] START {label}: {spec.instance_id}", flush=True)
        d = load_excel(spec.workbook, spec.instance_id)
        n = build_network(d)
        n, reduction_stats = reduce_network(d, n)
        (spec_out / "audit.txt").write_text(audit_report(d), encoding="utf8")
        (spec_out / "reduction.json").write_text(json.dumps(reduction_stats, indent=2), encoding="utf8")
        probabilities = d.probabilities[spec.scenario_set]
        result = solve_benders(
            d,
            n,
            probabilities,
            mode=METHOD,
            gap=args.mip_gap,
            max_iter=args.max_iter,
            time_limit=args.time_limit,
            master_time_limit=args.master_time_limit,
            output_dir=spec_out,
            parallel_scenarios=args.parallel_scenarios,
            max_scenario_workers=args.max_scenario_workers,
            solver_threads=args.solver_threads,
            nr_violation_tolerance=args.nr_violation_tolerance,
        )
        if args.audit_cuts:
            failures = cut_audit(d, n, probabilities, result["cut_records"])
            failures += cut_audit(d, n, probabilities, result["nr_cut_records"], relaxation=True)
            if failures:
                raise RuntimeError(f"cut audit failed for {spec.instance_id}: {failures[:3]}")
        if args.save_cuts:
            write_cut_records(spec_out / "benders_cuts.json", result)
        summary = {
            k: v
            for k, v in result.items()
            if k not in ("y", "cut_records", "nr_cut_records", "scenario_allocations")
        }
        summary.update(
            {
                "network": spec.network,
                "demand_level": spec.demand_level,
                "instance": spec.instance_id,
                "scenario_set": spec.scenario_set,
                "number_of_scenarios": len(probabilities),
                "cut_audit": "passed" if args.audit_cuts else "not_requested",
            }
        )
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    row = flatten_summary(spec, summary)
    rows.append(row)
    write_outputs(args.out, rows)
    elapsed = time.time() - started
    print(
        "[{}/{}] DONE {}: status={} time_s={} iter={} gap={} LB={} UB={} elapsed_s={:.1f}".format(
            index,
            total,
            label,
            row["termination_reason"],
            fmt(row["solution_time_seconds"]),
            fmt(row["benders_iterations"], 0),
            fmt(row["reported_gap"], 6),
            fmt(row["LB"], 6),
            fmt(row["UB"], 6),
            elapsed,
        ),
        flush=True,
    )


def write_readme(path: Path, run_count: int) -> None:
    lines = [
        "# 5.1.3 Algorithm Effectiveness Results",
        "",
        "This directory is produced by `tools/run_5_1_3_algorithm_effectiveness.py`.",
        "",
        "Default experiment design:",
        "",
        "- Method: BD-P-NR.",
        "- R04-R10: Y1/Y3/Y5 crossed with S10/S20/S30, 63 runs.",
        "- Sioux_Falls_30OD: Y1 crossed with S10/S20/S30, 3 runs.",
        "- Total default runs: 66.",
        "",
        f"Current aggregate rows: {run_count}.",
        "",
        "Main table fields:",
        "",
        "| Paper item | CSV column |",
        "|---|---|",
        "| UB | `UB` |",
        "| LB | `LB` |",
        "| Solution time | `solution_time_seconds` |",
        "| Benders iterations | `benders_iterations` |",
        "| Final gap | `reported_gap` |",
        "",
        "Use `report.md` for a quick human-readable table and `aggregate.csv` for paper-table processing.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def write_outputs(out: Path, rows: list[dict]) -> None:
    write_rows(out / "aggregate.csv", rows)
    (out / "aggregate.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
    write_markdown(out / "report.md", rows)
    write_readme(out / "README.md", len(rows))


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.1.3 algorithm-effectiveness experiments.")
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_1_3_algorithm_effectiveness")
    parser.add_argument("--instances", nargs="+", default=list(NETWORKS), choices=list(NETWORKS))
    parser.add_argument("--demands", nargs="+", default=list(DEMAND_LEVELS))
    parser.add_argument("--scenario-sets", nargs="+", default=list(SCENARIO_SETS))
    parser.add_argument("--include-sioux", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sioux-demands", nargs="+", default=["Y1"])
    parser.add_argument("--sioux-scenario-sets", nargs="+", default=list(SCENARIO_SETS))
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

    args.demands = parse_subset(args.demands, DEMAND_LEVELS, "demands")
    args.scenario_sets = parse_subset(args.scenario_sets, SCENARIO_SETS, "scenario sets")
    args.sioux_demands = parse_subset(args.sioux_demands, DEMAND_LEVELS, "Sioux demands")
    args.sioux_scenario_sets = parse_subset(args.sioux_scenario_sets, SCENARIO_SETS, "Sioux scenario sets")

    specs = build_specs(args, repo_root)
    rows: list[dict] = []
    total = len(specs)
    for index, spec in enumerate(specs, start=1):
        run_spec(spec, args, rows, index, total)
    if not args.dry_run:
        write_outputs(args.out, rows)
        print(json.dumps({"out": str(args.out), "runs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
