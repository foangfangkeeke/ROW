from __future__ import annotations
from dataclasses import dataclass
from .data import Data


@dataclass(frozen=True)
class Arc:
 key: tuple; tail: tuple; head: tuple; layer: str; physical: int|None; time: int|None; cost: float


@dataclass
class Network:
 arcs: dict[tuple[int,str],list[Arc]]
 nodes: dict[tuple[int,str],set[tuple]]
 protected: dict[tuple[int,int],list[tuple[int,int]]]
 reduction_stats: dict|None=None


def build_network(d: Data, reductions=None) -> Network:
 """Construct commodity networks and apply paper Sections 3.3 and 5.2 R1--R3."""
 arcs, nodes, protected = {}, {}, {}
 stats = {name: {'enabled': True if reductions is None else getattr(reductions, attr),
                 'arcs_before': 0, 'arcs_after': 0}
          for name, attr in (('R1_shortest_time', 'R1_shortest_time'),
                             ('R2_reachability', 'R2_reachability'),
                             ('R3_budget_paths', 'R3_budget_paths'))}
 horizon = max(d.periods) + 1
 candidates = set(d.candidates)
 for a, x in d.arcs.items():
  for t in d.periods:
   tau = int(x['autonomous_travel_periods'])
   if t + tau <= horizon:
    protected[a, t] = list(dict.fromkeys(d.row_cell(a, s) for s in range(t, t + tau)))

 def physical_dist(source, layer, reverse=False):
  """Positive-duration physical graph shortest paths, with A restricted to L^A."""
  dist = {source: 0}
  eligible = []
  for x in d.arcs.values():
   if layer == 'A' and not int(x.get('ROW_candidate', 1)):
    continue
   eligible.append((int(x['tail']), int(x['head']), int(x['autonomous_travel_periods'] if layer == 'A' else x['conventional_travel_periods'])))
  for _ in range(len(d.nodes) - 1):
   changed = False
   for u, v, weight in eligible:
    if reverse:
     u, v = v, u
    if u in dist and dist[u] + weight < dist.get(v, float('inf')):
     dist[v] = dist[u] + weight
     changed = True
   if not changed:
    break
  return dist

 def reachable(travel, origin, destination, release, deadline):
  forward = {(origin, t) for t in range(release, deadline + 1)}
  for e in sorted(travel, key=lambda z: z.tail[1]):
   if e.tail in forward:
    forward.add(e.head)
  backward = {(destination, t) for t in range(release, deadline + 1)}
  for e in sorted(travel, key=lambda z: z.tail[1], reverse=True):
   if e.head in backward:
    backward.add(e.tail)
  return forward, backward, [e for e in travel if e.tail in forward and e.head in backward]

 for k, c in d.commodities.items():
  origin, destination = int(c['origin']), int(c['destination'])
  release, deadline = int(c['release_period']), int(c['deadline_period'])
  for layer in ('A', 'H'):
   taufield = 'autonomous_travel_periods' if layer == 'A' else 'conventional_travel_periods'
   costfield = 'autonomous_unit_cost' if layer == 'A' else 'conventional_unit_cost'
   to_node = physical_dist(origin, layer)
   from_node = physical_dist(destination, layer, reverse=True)
   travel = []
   for a, x in d.arcs.items():
    tau = int(x[taufield])
    for t in range(release, deadline + 1):
     if t + tau > deadline:
      continue
     if layer == 'A' and ((a, t) not in protected or not all(cell in candidates for cell in protected[a, t])):
      continue
     travel.append(Arc(('T', k, layer, a, t), (int(x['tail']), t), (int(x['head']), t + tau), layer, a, t, float(x[costfield])))
   stats['R1_shortest_time']['arcs_before'] += len(travel)
   use_r1 = True if reductions is None else reductions.R1_shortest_time
   if use_r1:
    travel = [e for e in travel
              if release + to_node.get(e.tail[0], float('inf')) <= e.tail[1] <= deadline - from_node.get(e.tail[0], float('inf'))
              and release + to_node.get(e.head[0], float('inf')) <= e.head[1] <= deadline - from_node.get(e.head[0], float('inf'))]
   stats['R1_shortest_time']['arcs_after'] += len(travel)
   use_r2 = True if reductions is None else reductions.R2_reachability
   forward, backward, kept = reachable(travel, origin, destination, release, deadline)
   stats['R2_reachability']['arcs_before'] += len(travel)
   if not use_r2:
    kept = travel
   stats['R2_reachability']['arcs_after'] += len(kept)
   r3_input = len(kept)
   use_r3 = True if reductions is None else reductions.R3_budget_paths
   if layer == 'A' and use_r3:
    budget = float(d.params['resource_budget'])
    while kept:
     multiplicity = {}
     for e in kept:
      for cell in protected[e.physical, e.time]:
       multiplicity[cell] = multiplicity.get(cell, 0) + 1
     def weight(e):
      return sum(float(d.resource(cell)) / multiplicity[cell] for cell in protected[e.physical, e.time])
     fw = {(origin, t): 0. for t in range(release, deadline + 1)}
     for e in sorted(kept, key=lambda z: z.tail[1]):
      if e.tail in fw:
       fw[e.head] = min(fw.get(e.head, float('inf')), fw[e.tail] + weight(e))
     bw = {(destination, t): 0. for t in range(release, deadline + 1)}
     for e in sorted(kept, key=lambda z: z.tail[1], reverse=True):
      if e.head in bw:
       bw[e.tail] = min(bw.get(e.tail, float('inf')), bw[e.head] + weight(e))
     pruned = [e for e in kept if fw.get(e.tail, float('inf')) + weight(e) + bw.get(e.head, float('inf')) <= budget + 1e-9]
     if len(pruned) == len(kept):
      break
     kept = pruned
    # The revised paper reapplies R2 after R3 to remove disconnected states.
    if use_r2:
     forward, backward, kept = reachable(kept, origin, destination, release, deadline)
   if layer == 'A':
    stats['R3_budget_paths']['arcs_before'] += r3_input
    stats['R3_budget_paths']['arcs_after'] += len(kept)
   if use_r2:
    forward, backward, _ = reachable(kept, origin, destination, release, deadline)
   else:
    forward = {e.tail for e in kept} | {e.head for e in kept}
    backward = forward
   out = []
   ns = {('src', k, layer), ('sink', k, layer)}
   for t in range(release, deadline + 1):
    q = (origin, t)
    if q in backward:
     ns.add(q); out.append(Arc(('D', k, layer, t), ('src', k, layer), q, layer, None, t, 0.))
    q = (destination, t)
    if q in forward:
     ns.add(q); out.append(Arc(('X', k, layer, t), q, ('sink', k, layer), layer, None, t, 0.))
   for e in kept:
    ns.update((e.tail, e.head)); out.append(e)
   arcs[k, layer], nodes[k, layer] = out, ns
 return Network(arcs, nodes, protected, stats)
