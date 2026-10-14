from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from section5_2_common import DEMAND_LEVELS, POLICY_ORDER, add_instance_arguments, write_aggregate


SCRIPT_BY_POLICY = {
    "no_row": "run_5_2_no_row.py",
    "static_row": "run_5_2_static_row.py",
    "ave_row": "run_5_2_ave_row.py",
    "stochastic_row": "run_5_2_stochastic_row.py",
}


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run Section 5.2 ROW value policies.")
    add_instance_arguments(parser)
    parser.add_argument("--demand-levels", nargs="+", default=DEMAND_LEVELS, choices=DEMAND_LEVELS)
    parser.add_argument("--out", type=Path, default=project_root / "results" / "section5_2_row_value")
    parser.add_argument("--policies", nargs="+", default=POLICY_ORDER, choices=POLICY_ORDER)
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

    solve_args = [
        "--mip-gap",
        str(args.mip_gap),
        "--time-limit",
        str(args.time_limit),
        "--master-time-limit",
        str(args.master_time_limit),
        "--max-iter",
        str(args.max_iter),
        "--nr-violation-tolerance",
        str(args.nr_violation_tolerance),
    ]
    if args.audit_cuts:
        solve_args.append("--audit-cuts")
    if args.force:
        solve_args.append("--force")

    demand_levels = args.demand_levels
    total = len(demand_levels) * len(args.policies)
    index = 0
    for demand_level in demand_levels:
        demand_out = args.out / demand_level
        common = [
            "--network",
            args.network,
            "--demand-level",
            demand_level,
            "--scenario-set",
            args.scenario_set,
            "--out",
            str(demand_out),
            "--max-scenario-workers",
            str(args.max_scenario_workers),
            "--solver-threads",
            str(args.solver_threads),
        ]
        common.append("--parallel-scenarios" if args.parallel_scenarios else "--no-parallel-scenarios")
        if args.dry_run:
            common.append("--dry-run")
        for policy in args.policies:
            index += 1
            started = time.time()
            print(f"[{index}/{total}] START {demand_level}/{policy}", flush=True)
            cmd = [sys.executable, str(Path(__file__).with_name(SCRIPT_BY_POLICY[policy])), *common]
            if policy != "no_row":
                cmd.extend(solve_args)
            subprocess.run(cmd, check=True)
            print(f"[{index}/{total}] DONE {demand_level}/{policy}: elapsed_s={time.time() - started:.1f}", flush=True)

    if not args.dry_run:
        rows = []
        for demand_level in demand_levels:
            rows.extend(json.loads((args.out / demand_level / "aggregate.json").read_text(encoding="utf8")))
        write_aggregate(args.out, rows)


if __name__ == "__main__":
    main()
