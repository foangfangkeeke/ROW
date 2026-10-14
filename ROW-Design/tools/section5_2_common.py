from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from row.data import Data, audit_report, load_excel
from row.network import Network, build_network
from row.reduction import reduce_network
from row.subproblem import Recourse


DEFAULT_NETWORK = "Sioux_Falls_30OD"
DEFAULT_DEMAND_LEVEL = "Y1"
DEFAULT_SCENARIO_SET = "S10"
DEMAND_LEVELS = ["Y1", "Y3", "Y5"]
METHOD = "BD-P-NR"
POLICY_ORDER = ["no_row", "static_row", "ave_row", "stochastic_row"]


def instance_id(network: str, demand_level: str, scenario_set: str) -> str:
    return f"{network}_{demand_level}_{scenario_set}_H1_M10"


def add_instance_arguments(parser) -> None:
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--demand-level", default=DEFAULT_DEMAND_LEVEL)
    parser.add_argument("--scenario-set", default=DEFAULT_SCENARIO_SET, choices=["S10", "S20", "S30"])


def design_context(d: Data, network: str, demand_level: str, scenario_set: str) -> dict[str, Any]:
    return {
        "network": network,
        "demand_level": demand_level,
        "scenario_set": scenario_set,
        "instance_id": d.instance_id,
    }


def load_base_instance(repo_root: Path, network: str, demand_level: str, scenario_set: str) -> tuple[Data, Network, dict]:
    workbook = repo_root / "数据" / f"{network}_ROW_H1_M10.xlsx"
    d = load_excel(workbook, instance_id(network, demand_level, scenario_set))
    n = build_network(d)
    n, reduction_stats = reduce_network(d, n)
    return d, n, reduction_stats


def zero_schedule(d: Data) -> dict[tuple[int, int], float]:
    return {cell: 0.0 for cell in d.candidates}


def load_schedule(path: Path, candidates: list[tuple[int, int]]) -> dict[tuple[int, int], float]:
    y = {cell: 0.0 for cell in candidates}
    with path.open(newline="", encoding="utf8") as f:
        for row in csv.DictReader(f):
            cell = (int(row["arc_id"]), int(row["period"]))
            if cell in y:
                y[cell] = float(row.get("selected", 1.0))
    return y


def write_schedule(path: Path, y: dict[tuple[int, int], float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.writer(f)
        writer.writerow(["arc_id", "period", "selected"])
        writer.writerows((a, t, v) for (a, t), v in sorted(y.items()) if v > 0.5)


def make_average_data(d: Data, probabilities: dict[int, float], scenario_set: str) -> Data:
    scenario_id = 0
    scenarios = {scenario_id: {"scenario_id": scenario_id, "name": f"average_{scenario_set}"}}
    demand = {
        (scenario_id, k): sum(probabilities[s] * d.demand[s, k] for s in probabilities)
        for k in d.commodities
    }
    cap = {}
    for a in d.arcs:
        for t in d.periods:
            ua = sum(probabilities[s] * d.cap[s, a, t][0] for s in probabilities)
            rh = sum(probabilities[s] * d.cap[s, a, t][1] for s in probabilities)
            cap[scenario_id, a, t] = (ua, rh)
    return replace(
        d,
        scenarios=scenarios,
        demand=demand,
        cap=cap,
        probabilities={"AVG": {scenario_id: 1.0}},
        instance_id=f"{d.instance_id}_average_{scenario_set}",
    )


def _flow_values(d: Data, n: Network, values: list[float]):
    index = 0
    for k in d.commodities:
        for layer in ("A", "H"):
            index += 1
            for arc in n.arcs[k, layer]:
                yield k, layer, arc, values[index]
                index += 1
        index += 1


def _physical_arc_row(d: Data, arc_id: int) -> dict[str, Any]:
    arc = d.arcs[arc_id]
    return {"arc_id": arc_id, "tail": int(arc["tail"]), "head": int(arc["head"])}


def _h_capacity_delta(d: Data, arc_id: int, row_cell: tuple[int, int]) -> float:
    if row_cell not in d.candidates:
        return 0.0
    arc = d.arcs[arc_id]
    base = arc.get("base_capacity_per_period", arc.get("base_capacity_per_15min", 0.0))
    return float(d.params["ROW_capacity_share"]) * float(base)


def evaluate_schedule(
    d: Data,
    n: Network,
    probabilities: dict[int, float],
    y: dict[tuple[int, int], float],
    *,
    parallel_scenarios: bool = True,
    max_scenario_workers: int = 4,
    solver_threads: int = 1,
) -> dict[str, Any]:
    def one(s: int) -> dict[str, Any]:
        return {"scenario": s, **Recourse(d, n, s).solve(y, solver_threads=solver_threads)}

    if parallel_scenarios and len(probabilities) > 1:
        with ThreadPoolExecutor(max_workers=min(max_scenario_workers, len(probabilities))) as pool:
            scenario_reports = list(pool.map(one, probabilities))
    else:
        scenario_reports = [one(s) for s in probabilities]

    fixed_cost = sum(d.activation_cost(cell) * value for cell, value in y.items())
    resource_usage = sum(d.resource(cell) * value for cell, value in y.items())
    open_cells = [cell for cell, value in y.items() if value > 0.5]
    open_arcs = {cell[0] for cell in open_cells}
    budget = float(d.params["resource_budget"])
    fixed_cost_by_arc = {
        a: sum(d.activation_cost(cell) * y.get(cell, 0.0) for cell in d.candidates if cell[0] == a)
        for a in d.arcs
    }
    resource_by_arc = {
        a: sum(d.resource(cell) * y.get(cell, 0.0) for cell in d.candidates if cell[0] == a)
        for a in d.arcs
    }
    open_cells_by_arc = {a: sum(1 for cell in open_cells if cell[0] == a) for a in d.arcs}
    expected_link = {
        a: {
            **_physical_arc_row(d, a),
            "expected_A_flow": 0.0,
            "expected_H_flow": 0.0,
            "expected_A_transport_cost": 0.0,
            "expected_H_transport_cost": 0.0,
            "expected_row_entering_flow": 0.0,
            "expected_row_entry_capacity": 0.0,
            "open_lane_hours": open_cells_by_arc[a],
            "fixed_cost": fixed_cost_by_arc[a],
            "ROW_resource_usage": resource_by_arc[a],
            "weighted_budget_usage": resource_by_arc[a] / budget,
        }
        for a in d.arcs
    }
    scenario_link_metrics = []
    scenario_arc_period_metrics = []
    totals = {
        "expected_recourse_cost": 0.0,
        "A_transport_cost": 0.0,
        "H_transport_cost": 0.0,
        "outsourcing_cost": 0.0,
        "demand": 0.0,
        "A_volume": 0.0,
        "H_volume": 0.0,
        "E_volume": 0.0,
        "release_to_delivery_periods_x_units": 0.0,
        "delivered_network_units": 0.0,
        "network_transport_periods_x_units": 0.0,
        "network_transport_units": 0.0,
        "row_entering_flow": 0.0,
        "row_entry_capacity": 0.0,
    }
    compact_reports = []
    for report in scenario_reports:
        s = report["scenario"]
        probability = probabilities[s]
        totals["expected_recourse_cost"] += probability * report["value"]
        allocations = report["allocations"]
        for k, modes in allocations.items():
            demand = d.demand[s, k]
            totals["demand"] += probability * demand
            for mode in ("A", "H", "E"):
                totals[f"{mode}_volume"] += probability * modes[mode]
            totals["outsourcing_cost"] += probability * modes["E"] * float(d.commodities[k]["emergency_unit_cost"])

        period_metrics = {}
        for a in d.arcs:
            for t in d.periods:
                row_cell = d.row_cell(a, t)
                protected = n.protected.get((a, t), [])
                row_selected = min((y.get(cell, 0.0) for cell in protected), default=0.0)
                row_capacity, h_capacity_before = d.cap[s, a, t]
                h_capacity_after = h_capacity_before - _h_capacity_delta(d, a, row_cell) * y.get(row_cell, 0.0)
                period_metrics[a, t] = {
                    "scenario": s,
                    **_physical_arc_row(d, a),
                    "period": t,
                    "row_cell": row_cell[1] if row_cell in d.candidates else "",
                    "row_selected": row_selected,
                    "A_flow": 0.0,
                    "H_flow": 0.0,
                    "A_transport_cost": 0.0,
                    "H_transport_cost": 0.0,
                    "row_entry_capacity": row_capacity * row_selected,
                    "row_entering_flow": 0.0,
                    "row_entry_capacity_utilization": None,
                    "H_capacity_after_row": h_capacity_after,
                }
        for k, layer, arc, value in _flow_values(d, n, report["flows"]):
            if value <= 1e-8:
                continue
            if arc.physical is not None:
                totals[f"{layer}_transport_cost"] += probability * value * arc.cost
                totals["network_transport_periods_x_units"] += probability * value * (arc.head[1] - arc.tail[1])
                totals["network_transport_units"] += probability * value
                row = period_metrics[arc.physical, arc.time]
                row[f"{layer}_flow"] += value
                row[f"{layer}_transport_cost"] += value * arc.cost
                if layer == "A":
                    row["row_entering_flow"] += value
            elif arc.key[0] == "X":
                release = int(d.commodities[k]["release_period"])
                totals["release_to_delivery_periods_x_units"] += probability * value * (arc.tail[1] - release)
                totals["delivered_network_units"] += probability * value

        link_by_arc = {
            a: {
                "scenario": s,
                **_physical_arc_row(d, a),
                "A_flow": 0.0,
                "H_flow": 0.0,
                "A_transport_cost": 0.0,
                "H_transport_cost": 0.0,
                "row_entering_flow": 0.0,
                "row_entry_capacity": 0.0,
                "row_entry_capacity_utilization": None,
                "open_lane_hours": open_cells_by_arc[a],
                "fixed_cost": fixed_cost_by_arc[a],
                "ROW_resource_usage": resource_by_arc[a],
                "weighted_budget_usage": resource_by_arc[a] / budget,
            }
            for a in d.arcs
        }
        for row in period_metrics.values():
            if row["row_entry_capacity"] > 1e-8:
                row["row_entry_capacity_utilization"] = row["row_entering_flow"] / row["row_entry_capacity"]
                totals["row_entering_flow"] += probability * row["row_entering_flow"]
                totals["row_entry_capacity"] += probability * row["row_entry_capacity"]
            link = link_by_arc[row["arc_id"]]
            for key in ("A_flow", "H_flow", "A_transport_cost", "H_transport_cost", "row_entering_flow", "row_entry_capacity"):
                link[key] += row[key]
        for link in link_by_arc.values():
            if link["row_entry_capacity"] > 1e-8:
                link["row_entry_capacity_utilization"] = link["row_entering_flow"] / link["row_entry_capacity"]
            expected = expected_link[link["arc_id"]]
            expected["expected_A_flow"] += probability * link["A_flow"]
            expected["expected_H_flow"] += probability * link["H_flow"]
            expected["expected_A_transport_cost"] += probability * link["A_transport_cost"]
            expected["expected_H_transport_cost"] += probability * link["H_transport_cost"]
            expected["expected_row_entering_flow"] += probability * link["row_entering_flow"]
            expected["expected_row_entry_capacity"] += probability * link["row_entry_capacity"]
        scenario_arc_period_metrics.extend(period_metrics[cell] for cell in sorted(period_metrics))
        scenario_link_metrics.extend(link_by_arc[a] for a in sorted(link_by_arc))
        compact_reports.append(
            {
                "scenario": s,
                "recourse_cost": report["value"],
                "allocations": allocations,
                "backend": report["backend"],
            }
        )

    objective = fixed_cost + totals["expected_recourse_cost"]
    demand = totals["demand"]
    expected_link_metrics = [expected_link[a] for a in sorted(expected_link)]
    for link in expected_link_metrics:
        if link["expected_row_entry_capacity"] > 1e-8:
            link["expected_row_entry_capacity_utilization"] = link["expected_row_entering_flow"] / link["expected_row_entry_capacity"]
        else:
            link["expected_row_entry_capacity_utilization"] = None
    return {
        "objective": objective,
        "fixed_cost": fixed_cost,
        "expected_recourse_cost": totals["expected_recourse_cost"],
        "A_transport_cost": totals["A_transport_cost"],
        "H_transport_cost": totals["H_transport_cost"],
        "outsourcing_cost": totals["outsourcing_cost"],
        "A_volume_share": None if demand == 0 else totals["A_volume"] / demand,
        "H_volume_share": None if demand == 0 else totals["H_volume"] / demand,
        "E_volume_share": None if demand == 0 else totals["E_volume"] / demand,
        "average_release_to_delivery_periods": None
        if totals["delivered_network_units"] == 0
        else totals["release_to_delivery_periods_x_units"] / totals["delivered_network_units"],
        "average_network_transport_periods": None
        if totals["network_transport_units"] == 0
        else totals["network_transport_periods_x_units"] / totals["network_transport_units"],
        "open_directed_arcs": len(open_arcs),
        "open_lane_hours": len(open_cells),
        "ROW_resource_usage": resource_usage,
        "weighted_budget_usage": resource_usage / float(d.params["resource_budget"]),
        "row_entering_flow": totals["row_entering_flow"],
        "row_entry_capacity": totals["row_entry_capacity"],
        "row_entry_capacity_utilization": None
        if totals["row_entry_capacity"] == 0
        else totals["row_entering_flow"] / totals["row_entry_capacity"],
        "scenario_reports": compact_reports,
        "expected_link_metrics": expected_link_metrics,
        "scenario_link_metrics": scenario_link_metrics,
        "scenario_arc_period_metrics": scenario_arc_period_metrics,
    }


def flatten(policy: str, design_summary: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    signed_gap = design_summary.get("gap", design_summary.get("reported_gap"))
    return {
        "network": design_summary.get("network"),
        "demand_level": design_summary.get("demand_level"),
        "scenario_set": design_summary.get("scenario_set"),
        "instance_id": design_summary.get("instance_id"),
        "policy": policy,
        "objective": evaluation["objective"],
        "fixed_cost": evaluation["fixed_cost"],
        "expected_recourse_cost": evaluation["expected_recourse_cost"],
        "A_transport_cost": evaluation["A_transport_cost"],
        "H_transport_cost": evaluation["H_transport_cost"],
        "outsourcing_cost": evaluation["outsourcing_cost"],
        "A_volume_share": evaluation["A_volume_share"],
        "H_volume_share": evaluation["H_volume_share"],
        "E_volume_share": evaluation["E_volume_share"],
        "average_release_to_delivery_periods": evaluation["average_release_to_delivery_periods"],
        "average_network_transport_periods": evaluation["average_network_transport_periods"],
        "open_directed_arcs": evaluation["open_directed_arcs"],
        "open_lane_hours": evaluation["open_lane_hours"],
        "ROW_resource_usage": evaluation["ROW_resource_usage"],
        "weighted_budget_usage": evaluation["weighted_budget_usage"],
        "row_entering_flow": evaluation["row_entering_flow"],
        "row_entry_capacity": evaluation["row_entry_capacity"],
        "row_entry_capacity_utilization": evaluation["row_entry_capacity_utilization"],
        "design_time_seconds": design_summary.get("seconds"),
        "design_iterations": design_summary.get("iterations"),
        "design_gap": None if signed_gap is None else max(0.0, float(signed_gap)),
        "design_status": design_summary.get("termination_reason"),
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf8")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_policy_outputs(policy_out: Path, y: dict[tuple[int, int], float], design_summary: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    policy_out.mkdir(parents=True, exist_ok=True)
    write_schedule(policy_out / "row_schedule.csv", y)
    write_json(policy_out / "design_summary.json", design_summary)
    bulky = {"scenario_reports", "expected_link_metrics", "scenario_link_metrics", "scenario_arc_period_metrics"}
    write_json(policy_out / "evaluation.json", {k: v for k, v in evaluation.items() if k not in bulky})
    write_json(policy_out / "scenario_reports.json", evaluation["scenario_reports"])
    write_rows(policy_out / "expected_link_metrics.csv", evaluation["expected_link_metrics"])
    write_rows(policy_out / "scenario_link_metrics.csv", evaluation["scenario_link_metrics"])
    write_rows(policy_out / "scenario_arc_period_metrics.csv", evaluation["scenario_arc_period_metrics"])
    return flatten(policy_out.name, design_summary, evaluation)


def write_aggregate(out: Path, rows: list[dict[str, Any]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with (out / "aggregate.csv").open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(out / "aggregate.json", rows)
    lines = [
        "# Section 5.2 ROW Value and Stochasticity",
        "",
        "| Demand | Scenarios | Policy | Total cost | Fixed | A cost | H cost | Outsource | A share | H share | E share | Open arcs | Lane-hours | Budget use | ROW util | Design s | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {demand_level} | {scenario_set} | {policy} | {objective:.3f} | {fixed_cost:.3f} | {A_transport_cost:.3f} | {H_transport_cost:.3f} | {outsourcing_cost:.3f} | {A_volume_share:.4f} | {H_volume_share:.4f} | {E_volume_share:.4f} | {open_directed_arcs} | {open_lane_hours} | {weighted_budget_usage:.4f} | {row_util} | {design_time} | {status} |".format(
                demand_level=row["demand_level"],
                scenario_set=row["scenario_set"],
                policy=row["policy"],
                objective=row["objective"],
                fixed_cost=row["fixed_cost"],
                A_transport_cost=row["A_transport_cost"],
                H_transport_cost=row["H_transport_cost"],
                outsourcing_cost=row["outsourcing_cost"],
                A_volume_share=row["A_volume_share"],
                H_volume_share=row["H_volume_share"],
                E_volume_share=row["E_volume_share"],
                open_directed_arcs=row["open_directed_arcs"],
                open_lane_hours=row["open_lane_hours"],
                weighted_budget_usage=row["weighted_budget_usage"],
                row_util="" if row["row_entry_capacity_utilization"] is None else f"{row['row_entry_capacity_utilization']:.4f}",
                design_time="" if row["design_time_seconds"] is None else f"{row['design_time_seconds']:.3f}",
                status=row["design_status"],
            )
        )
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf8")


def upsert_aggregate(out: Path, row: dict[str, Any]) -> None:
    path = out / "aggregate.json"
    rows = json.loads(path.read_text(encoding="utf8")) if path.exists() else []
    by_policy = {item["policy"]: item for item in rows}
    by_policy[row["policy"]] = row
    ordered = [by_policy[name] for name in POLICY_ORDER if name in by_policy]
    ordered.extend(item for name, item in sorted(by_policy.items()) if name not in POLICY_ORDER)
    write_aggregate(out, ordered)


def write_base_metadata(out: Path, d: Data, reduction_stats: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.txt").write_text(audit_report(d), encoding="utf8")
    write_json(out / "reduction.json", reduction_stats)
