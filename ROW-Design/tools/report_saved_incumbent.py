"""Generate full scenario reports from a saved Benders incumbent schedule.

This is useful when an experiment's algorithm time limit has been reached and
the user wants to move on before the (potentially expensive) reporting phase.
It never changes the saved ROW schedule or reruns Benders.
"""
from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from row.config import load_config
from row.data import load_excel
from row.network import build_network
from row.reduction import reduce_network
from row.validation import scenario_diagnostics


def load_schedule(path: Path, candidates: list[tuple[int, int]]) -> dict[tuple[int, int], float]:
    y = {cell: 0.0 for cell in candidates}
    with path.open(newline="", encoding="utf8") as f:
        for row in csv.DictReader(f):
            cell = (int(row["arc_id"]), int(row["period"]))
            if cell in y:
                y[cell] = float(row.get("selected", 1.0))
    return y


def main() -> None:
    parser = argparse.ArgumentParser(description="Report a saved ROW incumbent")
    parser.add_argument("excel")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--schedule", default="row_schedule_incumbent.csv")
    args = parser.parse_args()

    out = Path(args.out)
    cfg = load_config(args.config)
    d = load_excel(args.excel)
    n = build_network(d, cfg.reductions)
    n, _ = reduce_network(d, n, cfg.reductions)
    y = load_schedule(out / args.schedule, d.candidates)
    scenario_ids = list(d.probabilities[cfg.scenario_set])
    workers = min(cfg.max_scenario_workers, len(scenario_ids)) if cfg.parallel_scenarios else 1
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            diagnostics = list(pool.map(lambda s: scenario_diagnostics(d, n, s, y), scenario_ids))
    else:
        diagnostics = [scenario_diagnostics(d, n, s, y) for s in scenario_ids]

    allocations = {x["scenario"]: x["allocations"] for x in diagnostics}
    capacity = [{"scenario": x["scenario"], "residuals": x["capacity_residuals"]} for x in diagnostics]
    compact = [{k: v for k, v in x.items() if k != "capacity_residuals"} for x in diagnostics]
    (out / "scenario_allocations.json").write_text(json.dumps(allocations, indent=2), encoding="utf8")
    (out / "capacity_residuals.json").write_text(json.dumps(capacity, indent=2), encoding="utf8")
    (out / "scenario_diagnostics.json").write_text(json.dumps(compact, indent=2), encoding="utf8")

    first = sum(float(d.arcs[a]["ROW_activation_cost_per_period"]) * v for (a, _), v in y.items())
    recourse = sum(d.probabilities[cfg.scenario_set][x["scenario"]] * x["recourse_cost"] for x in diagnostics)
    report = {
        "report_source": "saved_incumbent",
        "first_stage_cost_recomputed": first,
        "expected_recourse_cost_recomputed": recourse,
        "objective_recomputed": first + recourse,
        "scenario_count": len(diagnostics),
        "parallel_scenarios": bool(workers > 1),
        "scenario_workers": workers,
    }
    (out / "postprocess_summary.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
