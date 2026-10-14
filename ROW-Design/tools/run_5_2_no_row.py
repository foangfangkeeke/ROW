from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from section5_2_common import (
    add_instance_arguments,
    design_context,
    evaluate_schedule,
    load_base_instance,
    upsert_aggregate,
    write_base_metadata,
    write_policy_outputs,
    zero_schedule,
)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    parser = argparse.ArgumentParser(description="Run Section 5.2 No ROW baseline.")
    add_instance_arguments(parser)
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_2_row_value")
    parser.add_argument("--max-scenario-workers", type=int, default=4)
    parser.add_argument("--solver-threads", type=int, default=1)
    parser.add_argument("--parallel-scenarios", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[1/1] no_row: fixed y=0, evaluated on {args.network}/{args.demand_level}/{args.scenario_set}")
        return

    d, n, reduction_stats = load_base_instance(repo_root, args.network, args.demand_level, args.scenario_set)
    write_base_metadata(args.out, d, reduction_stats)
    started = time.time()
    print("[1/1] START no_row", flush=True)
    y = zero_schedule(d)
    design_summary = {
        "method": "fixed_zero",
        "seconds": 0.0,
        "iterations": 0,
        "termination_reason": "not_optimized",
        "gap": None,
    }
    design_summary.update(design_context(d, args.network, args.demand_level, args.scenario_set))
    evaluation = evaluate_schedule(
        d,
        n,
        d.probabilities[args.scenario_set],
        y,
        parallel_scenarios=args.parallel_scenarios,
        max_scenario_workers=args.max_scenario_workers,
        solver_threads=args.solver_threads,
    )
    row = write_policy_outputs(args.out / "no_row", y, design_summary, evaluation)
    upsert_aggregate(args.out, row)
    print(
        "[1/1] DONE no_row: objective={:.3f} A_share={:.4f} H_share={:.4f} E_share={:.4f} elapsed_s={:.1f}".format(
            row["objective"],
            row["A_volume_share"],
            row["H_volume_share"],
            row["E_volume_share"],
            time.time() - started,
        ),
        flush=True,
    )
    print(json.dumps({"out": str(args.out), "policy": "no_row"}, indent=2))


if __name__ == "__main__":
    main()
