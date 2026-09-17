from __future__ import annotations
import time
from .data import Data
from .network import Network


def reduce_network(d: Data, n: Network, options=None):
 """Report R1--R3 preprocessing without changing the paper's candidate set C.

 The September 16 manuscript has three reduction rules.  In particular, R3
 may remove an autonomous commodity network, but it must not fix unused ROW
 design cells: C and the first-stage feasible region remain unchanged.
 """
 started = time.time()
 before = len(d.candidates)
 impossible = [k for k in d.commodities if not any(e.physical is not None for e in n.arcs[k, 'A'])]
 stats = dict(n.reduction_stats or {})
 stats.update({
   'candidate_cells_before': before,
   'candidate_cells_after': before,
   'time_space_arcs': sum(map(len, n.arcs.values())),
   'time_space_travel_arcs': sum(1 for ars in n.arcs.values() for e in ars if e.physical is not None),
   'fixed_autonomous_commodities': impossible,
   'preprocessing_seconds': time.time() - started,
 })
 return n, stats
