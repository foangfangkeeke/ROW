import itertools
import unittest
from pathlib import Path

from row.data import Data, audit
from row.network import build_network
from row.subproblem import Recourse
from row.extensive_form import solve_extensive
from row.benders import solve_benders
from row.validation import cut_audit


def toy(*, destination=2, tau_a=1, tau_h=1, candidates=None, row_capacity=10.0, conventional_capacity=10.0):
    """Small in-memory instance used to protect time-space modelling rules."""
    arcs = {1: {
        'arc_id': 1, 'tail': 1, 'head': 2, 'ROW_candidate': 1,
        'autonomous_travel_periods': tau_a, 'conventional_travel_periods': tau_h,
        'autonomous_unit_cost': 1.0, 'conventional_unit_cost': 2.0,
        'emergency_unit_cost': 100.0, 'ROW_resource_weight': 1.0,
        'ROW_activation_cost_per_period': 0.0, 'base_capacity_per_period': 10.0,
    }}
    periods = [1, 2, 3, 4]
    commodities = {1: {'commodity_id': 1, 'origin': 1, 'destination': destination,
                       'release_period': 1, 'deadline_period': 4, 'emergency_unit_cost': 100.0}}
    cap = {(1, 1, t): (row_capacity, conventional_capacity) for t in periods}
    return Data(Path('toy.xlsx'), {'resource_budget': 10.0, 'ROW_capacity_share': .1}, [1, 2, 3], arcs,
                commodities, periods, {1: {'scenario_id': 1}}, {(1, 1): 5.0}, cap,
                [(1, t) for t in periods] if candidates is None else candidates, {'S10': {1: 1.0}, 'S20': {}, 'S30': {}})


class TestTimeSpaceMicroCases(unittest.TestCase):
    def test_duration_three_uses_all_occupied_row_cells(self):
        d = toy(tau_a=3, tau_h=3); n = build_network(d)
        travel = [e for e in n.arcs[1, 'A'] if e.physical is not None]
        self.assertEqual([(e.tail, e.head) for e in travel], [((1, 1), (2, 4))])
        self.assertEqual(n.protected[1, 1], [(1, 1), (1, 2), (1, 3)])

    def test_no_intermediate_waiting_or_layer_transfer_arcs(self):
        d = toy(); n = build_network(d)
        for layer in ('A', 'H'):
            for e in n.arcs[1, layer]:
                if e.physical is not None:
                    self.assertGreater(e.head[1] - e.tail[1], 0)
                self.assertEqual(e.layer, layer)
        # The only virtual arcs are source dispatch and sink delivery.
        self.assertTrue(all(e.physical is not None or e.tail[0] == 'src' or e.head[0] == 'sink'
                            for e in n.arcs[1, 'A']))

    def test_emergency_guarantees_recourse_when_no_network_path(self):
        d = toy(destination=3); n = build_network(d)
        r = Recourse(d, n, 1).solve({cell: 0.0 for cell in d.candidates})
        self.assertAlmostEqual(r['value'], 500.0, places=6)
        self.assertAlmostEqual(r['allocations'][1]['E'], 5.0, places=6)

    def test_data_audit_rejects_conventional_capacity_loss_above_residual(self):
        d = toy(conventional_capacity=.5)
        with self.assertRaisesRegex(ValueError, 'delta > R_H'):
            audit(d)

    def test_three_binary_enumeration_extensive_and_benders_agree(self):
        d = toy(candidates=[(1, 1), (1, 2), (1, 3)])
        # A nonzero activation cost makes enumeration a genuine first-stage
        # trade-off rather than merely checking identical recourse LPs.
        d.arcs[1]['ROW_activation_cost_per_period'] = 3.0
        n = build_network(d)
        enumerated = min(
            3.0 * sum(bits) + Recourse(d, n, 1).solve(dict(zip(d.candidates, bits)))['value']
            for bits in itertools.product((0.0, 1.0), repeat=3)
        )
        ef = solve_extensive(d, n, {1: 1.0}, gap=1e-8)
        self.assertAlmostEqual(enumerated, ef['objective'], places=6)
        for mode in ('BD-P', 'BD-NR', 'BD-P-NR'):
            bd = solve_benders(d, n, {1: 1.0}, mode=mode, gap=1e-8, max_iter=20)
            self.assertAlmostEqual(enumerated, bd['objective'], places=6, msg=mode)
            self.assertLessEqual(bd['gap'], 1e-8, msg=mode)
            self.assertEqual([], cut_audit(d, n, {1: 1.0}, bd['cut_records']), msg=mode)
            self.assertEqual([], cut_audit(d, n, {1: 1.0}, bd['nr_cut_records'], relaxation=True), msg=mode)
