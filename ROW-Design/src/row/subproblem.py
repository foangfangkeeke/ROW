from __future__ import annotations
from collections import defaultdict
import cplex, os, re, subprocess, tempfile, xml.etree.ElementTree as ET
from .data import Data
from .network import Network
class Recourse:
 def __init__(self,d:Data,n:Network,scenario:int): self.d,self.n,self.s=d,n,scenario
 def solve(self,y:dict[tuple[int,int],float], write_lp=None, solver_threads=1, commodity_separable=False):
  d,n,s=self.d,self.n,self.s; m=cplex.Cplex(); m.set_log_stream(None);m.set_results_stream(None);m.set_warning_stream(None);m.set_error_stream(None);m.objective.set_sense(m.objective.sense.minimize)
  var=[]; obj=[]; lb=[]; flow={}; z={}
  for k in d.commodities:
   for layer in ('A','H'):
    z[k,layer]=len(var);var.append(f'z_{k}_{layer}');obj.append(0.);lb.append(0.)
    for e in n.arcs[k,layer]: flow[e.key]=len(var);var.append('f_'+'_'.join(map(str,e.key)));obj.append(e.cost);lb.append(0.)
   z[k,'E']=len(var);var.append(f'e_{k}');obj.append(float(d.commodities[k]['emergency_unit_cost']));lb.append(0.)
  m.variables.add(names=var,obj=obj,lb=lb)
  names=[]; rhs=[]; senses=[]; rows=[]; meta=[]
  # split and layer flow balances
  for k in d.commodities:
   rows.append(cplex.SparsePair([z[k,'A'],z[k,'H'],z[k,'E']],[1.,1.,1.]));rhs.append(d.demand[s,k]);senses.append('E');names.append(f'split_{k}');meta.append(('const',d.demand[s,k],{}))
   for layer in ('A','H'):
    for v in n.nodes[k,layer]:
     if v==('sink',k,layer): continue  # one redundant network-balance equation
     ind=[];val=[]
     for e in n.arcs[k,layer]:
      if e.tail==v: ind.append(flow[e.key]);val.append(1.)
      if e.head==v: ind.append(flow[e.key]);val.append(-1.)
     if v==('src',k,layer): ind.append(z[k,layer]);val.append(-1.)
     if v==('sink',k,layer): ind.append(z[k,layer]);val.append(1.)
     rows.append(cplex.SparsePair(ind,val));rhs.append(0.);senses.append('E');names.append(f'bal_{k}_{layer}_{v}');meta.append(('const',0.,{}))
  # In the exact model capacities are shared across commodities.  In the
  # Section 5.4 relaxation each commodity instead receives the full capacity.
  # Both forms retain the same affine RHS metadata, so coefficients are always
  # derived from W x >= h - T y rather than hand-coded signs.
  for layer in ('A','H'):
   for a,x in d.arcs.items():
    for t in d.periods:
     groups=([k] for k in d.commodities) if commodity_separable else [d.commodities]
     for group in groups:
      ind=[flow[e.key] for k in group for e in n.arcs[k,layer] if e.layer==layer and e.physical==a and e.time==t]
      if not ind: continue
      suffix=f'_k{next(iter(group))}' if commodity_separable else ''
      if layer=='A':
       if (a,t) not in n.protected: continue
       U,_=d.cap[s,a,t]
       for cell in n.protected[a,t]:
        rows.append(cplex.SparsePair(ind,[1.]*len(ind)));rhs.append(U*y.get(cell,0.));senses.append('L');names.append(f'A_{a}_{t}_{cell[1]}{suffix}');meta.append(('affine',0.,{cell:U} if cell in d.candidates else {}))
      else:
       _,R=d.cap[s,a,t]; cell=d.row_cell(a,t); delta=float(d.params['ROW_capacity_share'])*float(x.get('base_capacity_per_period',x.get('base_capacity_per_15min',0.))) if cell in d.candidates else 0.
       rows.append(cplex.SparsePair(ind,[1.]*len(ind)));rhs.append(R-delta*y.get(cell,0.));senses.append('L');names.append(f'H_{a}_{t}{suffix}');meta.append(('affine',R,{cell:-delta} if cell in d.candidates else {}))
  m.linear_constraints.add(lin_expr=rows,senses=senses,rhs=rhs,names=names)
  def primal_report(values):
   """Recompute auditable primal residuals from stable model indices."""
   allocations={k:{'A':values[z[k,'A']],'H':values[z[k,'H']],'E':values[z[k,'E']]} for k in d.commodities}
   residual=[sum(values[i]*v for i,v in zip(row.ind,row.val))-b for row,b in zip(rows,rhs)]
   capacity=[]
   for layer in ('A','H'):
    for a,x in d.arcs.items():
     for t in d.periods:
      usage=sum(values[flow[e.key]] for k in d.commodities for e in n.arcs[k,layer] if e.physical==a and e.time==t)
      if not usage and not any(e.physical==a and e.time==t for k in d.commodities for e in n.arcs[k,layer]): continue
      if layer=='A':
       if (a,t) not in n.protected: continue
       U,_=d.cap[s,a,t]
       for cell in n.protected[a,t]:
        capacity.append({'layer':'A','arc_id':a,'entry_period':t,'protected_cell':cell,'usage':usage,'capacity':U*y.get(cell,0.),'slack':U*y.get(cell,0.)-usage})
      else:
       _,R=d.cap[s,a,t]; cell=d.row_cell(a,t); delta=float(d.params['ROW_capacity_share'])*float(x.get('base_capacity_per_period',x.get('base_capacity_per_15min',0.))) if cell in d.candidates else 0.
       capacity.append({'layer':'H','arc_id':a,'entry_period':t,'usage':usage,'capacity':R-delta*y.get(cell,0.),'slack':R-delta*y.get(cell,0.)-usage})
   return {'allocations':allocations,'max_flow_balance_violation':max((abs(v) for v,sense in zip(residual,senses) if sense=='E'),default=0.),'min_capacity_slack':min((x['slack'] for x in capacity),default=0.),'capacity_residuals':capacity}
  if write_lp:
   m.write(str(write_lp)); return {'model':m,'variables':var,'rows':names,'meta':meta}
  m.parameters.threads.set(solver_threads)
  try:
   m.solve()
  except cplex.exceptions.CplexSolverError as exc:
   if '1016' not in str(exc): raise
   exe=os.environ.get('CPLEX_INTERACTIVE',r'C:\Program Files\IBM\ILOG\CPLEX_Studio222\cplex\bin\x64_win64\cplex.exe')
   if not os.path.exists(exe): raise RuntimeError('CPLEX Python Community Edition limit; no CPLEX interactive executable found') from exc
   with tempfile.TemporaryDirectory() as td:
    lp=os.path.join(td,'recourse.lp'); sol=os.path.join(td,'recourse.sol'); m.write(lp)
    out=subprocess.run([exe,'-c',f'read {lp}',f'set threads {solver_threads}','optimize',f'write {sol}','display solution objective','display solution dual *'],capture_output=True,text=True,encoding='utf-8',errors='replace',check=True).stdout
    if not os.path.exists(sol): raise RuntimeError('CPLEX Interactive did not write recourse solution:\n'+out)
    xml_values={v.attrib['name'].split('#')[0]:float(v.attrib['value']) for v in ET.parse(sol).getroot().findall('./variables/variable')}
   hit=re.findall(r'Objective\s*=\s*([-+0-9.eE]+)',out)
   if not hit: raise RuntimeError('could not parse CPLEX interactive objective:\n'+out[-2000:])
   objective=float(hit[-1]); dual_by_name={}
   for line in out.splitlines():
    q=re.match(r'^(\S+)\s+([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*$',line.strip())
    if q: dual_by_name[q.group(1).split('#')[0]]=float(q.group(2))
   pi=[dual_by_name.get(name,0.) for name in names]; alpha=0.; beta={}
   for dual,(kind,b,coef) in zip(pi,meta):
    alpha+=dual*b
    for cell,v in coef.items(): beta[cell]=beta.get(cell,0.)+dual*v
   values=[xml_values.get(name,0.) for name in var]
   # Interactive CPLEX may omit presolve-substituted mode variables from its
   # sparse XML solution.  Reconstruct those variables from the dispatch flow
   # identities, then close the demand split with emergency service.
   for k in d.commodities:
    for layer in ('A','H'):
     values[z[k,layer]]=sum(values[flow[e.key]] for e in n.arcs[k,layer] if e.tail==('src',k,layer))
    values[z[k,'E']]=d.demand[s,k]-values[z[k,'A']]-values[z[k,'H']]
   report=primal_report(values)
   return {'value':objective,'alpha':alpha,'beta':beta,'flows':values,'model':None,'names':names,'meta':meta,'backend':'CPLEX Interactive 22.2.0.0',**report}
  if m.solution.get_status() not in (1,101,102): raise RuntimeError('recourse infeasible: '+m.solution.get_status_string())
  pi=m.solution.get_dual_values(); alpha=0.;beta={}
  for dual,(kind,b,coef) in zip(pi,meta):
   alpha+=dual*b
   for cell,v in coef.items(): beta[cell]=beta.get(cell,0.)+dual*v
  values=m.solution.get_values()
  report=primal_report(values)
  return {'value':m.solution.get_objective_value(),'alpha':alpha,'beta':beta,'flows':values,'model':m,'names':names,'meta':meta,'backend':'CPLEX Python 22.2.0.0',**report}
