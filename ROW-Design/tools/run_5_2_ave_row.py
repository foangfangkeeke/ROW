from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from row.benders import solve_benders
from row.network import build_network
from row.reduction import reduce_network
from row.validation import cut_audit

from section5_2_common import (
    METHOD,
    add_instance_arguments,
    design_context,
    evaluate_schedule,
    load_base_instance,
    load_schedule,
    make_average_data,
    upsert_aggregate,
    write_base_metadata,
    write_json,
    write_policy_outputs,
)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.2 average ROW policy.")
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
        print(f"[1/1] ave_row: solve mean-demand/capacity single scenario, evaluate on {args.network}/{args.demand_level}/{args.scenario_set}")
        return

    d, n, reduction_stats = load_base_instance(repo_root, args.network, args.demand_level, args.scenario_set)
    write_base_metadata(args.out, d, reduction_stats)
    policy_out = args.out / "ave_row"
    policy_out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    print("[1/1] START ave_row", flush=True)
    summary_path = policy_out / "design_summary.json"
    schedule_path = policy_out / "row_schedule_incumbent.csv"
    if summary_path.exists() and schedule_path.exists() and not args.force:
        design_summary = json.loads(summary_path.read_text(encoding="utf8"))
        y = load_schedule(schedule_path, d.candidates)
    else:
        avg_data = make_average_data(d, d.probabilities[args.scenario_set], args.scenario_set)
        avg_network = build_network(avg_data)
        avg_network, avg_reduction = reduce_network(avg_data, avg_network)
        write_json(policy_out / "average_reduction.json", avg_reduction)
        result = solve_benders(
            avg_data,
            avg_network,
            avg_data.probabilities["AVG"],
            mode=METHOD,
            gap=args.mip_gap,
            max_iter=args.max_iter,
            time_limit=args.time_limit,
            master_time_limit=args.master_time_limit,
            output_dir=policy_out,
            parallel_scenarios=False,
            max_scenario_workers=1,
            solver_threads=args.solver_threads,
            nr_violation_tolerance=args.nr_violation_tolerance,
        )
        if args.audit_cuts:
            failures = cut_audit(avg_data, avg_network, avg_data.probabilities["AVG"], result["cut_records"])
            failures += cut_audit(avg_data, avg_network, avg_data.probabilities["AVG"], result["nr_cut_records"], relaxation=True)
            if failures:
                raise RuntimeError(f"cut audit failed for ave_row: {failures[:3]}")
        y = result["y"]
        design_summary = {
            k: v
            for k, v in result.items()
            if k not in ("y", "cut_records", "nr_cut_records", "scenario_allocations")
        }
        design_summary.update(design_context(d, args.network, args.demand_level, args.scenario_set))
        design_summary.update({"policy": "ave_row", "design_scenario_set": "AVG", "evaluation_scenario_set": args.scenario_set})
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
        "[1/1] DONE ave_row: objective={:.3f} gap={} elapsed_s={:.1f}".format(
            row["objective"],
            "" if row["design_gap"] is None else f"{row['design_gap']:.6f}",
            time.time() - started,
        ),
        flush=True,
    )
    print(json.dumps({"out": str(args.out), "policy": "ave_row"}, indent=2))


if __name__ == "__main__":
    main()
