from __future__ import annotations
from collections import deque, defaultdict

def minimum_cut(d, n, scenario, commodity):
 """Return a minimum autonomous controlled cut as physical-entry cells.

Travel arcs have their scenario autonomous entry capacities; dispatch/delivery
arcs receive a finite-but-dominating value.  The returned cut contains only
physical travel arcs, so z_A <= sum(U_at y_at) is implied by the base model.
"""
 arcs=n.arcs[commodity,'A']; src=('src',commodity,'A'); sink=('sink',commodity,'A')
 finite=sum(d.cap[scenario,e.physical,e.time][0] for e in arcs if e.physical is not None)+1.
 cap=defaultdict(float); adj=defaultdict(set)
 for e in arcs:
  w=d.cap[scenario,e.physical,e.time][0] if e.physical is not None else finite
  cap[e.tail,e.head]+=w; adj[e.tail].add(e.head);adj[e.head].add(e.tail)
 flow=defaultdict(float)
 while True:
  parent={src:None};q=deque([src])
  while q and sink not in parent:
   u=q.popleft()
   for v in adj[u]:
    if v not in parent and cap[u,v]-flow[u,v]>1e-9: parent[v]=u;q.append(v)
  if sink not in parent: break
  aug=float('inf');v=sink
  while parent[v] is not None: u=parent[v];aug=min(aug,cap[u,v]-flow[u,v]);v=u
  v=sink
  while parent[v] is not None: u=parent[v];flow[u,v]+=aug;flow[v,u]-=aug;v=u
 reachable={src};q=deque([src])
 while q:
  u=q.popleft()
  for v in adj[u]:
   if v not in reachable and cap[u,v]-flow[u,v]>1e-9:reachable.add(v);q.append(v)
 gamma={(e.physical,e.time) for e in arcs if e.physical is not None and e.tail in reachable and e.head not in reachable}
 return gamma

def selected_minimum_cuts(d,n,scenario):
 return {k:minimum_cut(d,n,scenario,k) for k in d.commodities if n.arcs[k,'A']}
