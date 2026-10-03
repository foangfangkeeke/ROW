from __future__ import annotations
import time, cplex
from .data import Data
from .network import Network
from .benders import _solve_master_interactive

def solve_extensive(d:Data,n:Network,scenarios:dict[int,float],gap=1e-6,time_limit=None,solver_threads=1):
 """Build the full deterministic-equivalent MILP with one shared ROW schedule."""
 started=time.time(); m=cplex.Cplex();m.set_log_stream(None);m.set_results_stream(None);m.set_warning_stream(None);m.set_error_stream(None);m.objective.set_sense(m.objective.sense.minimize)
 cells=list(d.candidates); names=[f'y_{a}_{t}' for a,t in cells]; yidx={z:i for i,z in enumerate(cells)}
 m.variables.add(names=names,obj=[d.activation_cost(cell) for cell in cells],types=['B']*len(cells),lb=[0.]*len(cells),ub=[1.]*len(cells))
 m.linear_constraints.add(
  lin_expr=[cplex.SparsePair(list(range(len(cells))),[d.resource(cell) for cell in cells])],
  senses=['L'],rhs=[float(d.params['resource_budget'])],names=['resource_budget'])
 rows=[]; rhs=[]; senses=[]; flowvars={}; zvars={}; all_names=list(names)
 for s,p in scenarios.items():
  flow={}; z={}
  for k in d.commodities:
   for layer in ('A','H'):
    z[k,layer]=len(all_names); all_names.append(f'z_{s}_{k}_{layer}')
    for e in n.arcs[k,layer]:
     flow[e.key]=len(all_names); all_names.append('f_'+str(s)+'_'+'_'.join(map(str,e.key)))
   z[k,'E']=len(all_names);all_names.append(f'e_{s}_{k}')
  # add this scenario's variables in exactly the same order as their names
  obj=[]; lb=[]
  for k in d.commodities:
   for layer in ('A','H'):
    obj.append(0.);lb.append(0.)
    obj.extend([p*e.cost for e in n.arcs[k,layer]]);lb.extend([0.]*len(n.arcs[k,layer]))
   obj.append(p*float(d.commodities[k]['emergency_unit_cost']));lb.append(0.)
  m.variables.add(names=all_names[len(m.variables.get_names()):],obj=obj,lb=lb)
  # mode split and flow balance
  for k in d.commodities:
   rows.append(cplex.SparsePair([z[k,'A'],z[k,'H'],z[k,'E']],[1.,1.,1.]));rhs.append(d.demand[s,k]);senses.append('E')
   for layer in ('A','H'):
    for v in n.nodes[k,layer]:
     if v==('sink',k,layer): continue
     ind=[];val=[]
     for e in n.arcs[k,layer]:
      if e.tail==v:ind.append(flow[e.key]);val.append(1.)
      if e.head==v:ind.append(flow[e.key]);val.append(-1.)
     if v==('src',k,layer):ind.append(z[k,layer]);val.append(-1.)
     if v==('sink',k,layer):ind.append(z[k,layer]);val.append(1.)
     rows.append(cplex.SparsePair(ind,val));rhs.append(0.);senses.append('E')
  for layer in ('A','H'):
   for a,x in d.arcs.items():
    for t in d.periods:
     ind=[flow[e.key] for k in d.commodities for e in n.arcs[k,layer] if e.physical==a and e.time==t]
     if not ind: continue
     if layer=='A':
      if (a,t) not in n.protected: continue
      U,_=d.cap[s,a,t]
      for cell in n.protected[a,t]:
       if cell in yidx: rows.append(cplex.SparsePair(ind+[yidx[cell]],[1.]*len(ind)+[-U]))
       else: rows.append(cplex.SparsePair(ind,[1.]*len(ind)))
       rhs.append(0.);senses.append('L')
     else:
      _,R=d.cap[s,a,t]; cell=d.row_cell(a,t);delta=float(d.params['ROW_capacity_share'])*float(x.get('base_capacity_per_period',x.get('base_capacity_per_15min',0.)))
      if cell in yidx: rows.append(cplex.SparsePair(ind+[yidx[cell]],[1.]*len(ind)+[delta]))
      else: rows.append(cplex.SparsePair(ind,[1.]*len(ind)))
      rhs.append(R);senses.append('L')
  flowvars[s]=flow;zvars[s]=z
 m.linear_constraints.add(lin_expr=rows,senses=senses,rhs=rhs)
 obj,lb,vals=_solve_master_interactive(m,all_names,gap,time_limit,solver_threads); y=dict(zip(cells,vals[:len(cells)])); first=sum(d.activation_cost(cell)*y[cell] for cell in cells)
 allocations={s:{k:{mode:vals[zvars[s][k,mode]] for mode in ('A','H','E')} for k in d.commodities} for s in scenarios}
 return {'objective':obj,'first_stage':first,'expected_recourse':obj-first,'LB':lb,'UB':obj,'gap':(obj-lb)/max(1.,abs(obj)),'iterations':1,'cuts':0,'ordinary_cuts':0,'pareto_cuts':0,'fallback_cuts':0,'master_solver_backends':[getattr(m,'_row_solver_backend','unknown')],'y':y,'scenario_allocations':allocations,'seconds':time.time()-started,'cut_records':[],'stopped_by_time_limit':False,'solver_threads_per_model':solver_threads}
