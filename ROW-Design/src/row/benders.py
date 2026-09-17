from __future__ import annotations
import time, cplex, os, subprocess, tempfile, xml.etree.ElementTree as ET, json, csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .subproblem import Recourse
from .pareto import select_pareto_cut

def _master(m,names,gap,limit,threads):
 try:
  m.parameters.threads.set(threads); m.parameters.mip.tolerances.mipgap.set(gap)
  if limit is not None: m.parameters.timelimit.set(max(1.,limit))
  m.solve()
  if not m.solution.is_primal_feasible(): raise RuntimeError('CPLEX master: '+m.solution.get_status_string())
  return m.solution.get_objective_value(),m.solution.MIP.get_best_objective(),m.solution.get_values(names)
 except cplex.exceptions.CplexSolverError as exc:
  if '1016' not in str(exc): raise
  exe=os.environ.get('CPLEX_INTERACTIVE',r'C:\Program Files\IBM\ILOG\CPLEX_Studio222\cplex\bin\x64_win64\cplex.exe')
  if not os.path.exists(exe): raise RuntimeError('CPLEX Community limit and no Interactive Optimizer') from exc
  with tempfile.TemporaryDirectory() as td:
   lp=os.path.join(td,'master.lp'); sol=os.path.join(td,'master.sol'); m.write(lp)
   cmd=[exe,'-c',f'read {lp}',f'set threads {threads}',f'set mip tolerances mipgap {gap}']
   if limit is not None: cmd.append(f'set timelimit {max(1.,limit)}')
   out=subprocess.run(cmd+['optimize',f'write {sol}'],capture_output=True,text=True,encoding='utf8',errors='replace',check=True).stdout
   if not os.path.exists(sol): raise RuntimeError('CPLEX Interactive failed:\n'+out[-2000:])
   root=ET.parse(sol).getroot(); header=root.find('header'); status=header.attrib.get('solutionStatusString','')
   if 'optimal' not in status.lower() and 'time limit' not in status.lower(): raise RuntimeError('CPLEX master: '+status)
   values={v.attrib['name'].split('#')[0]:float(v.attrib['value']) for v in root.findall('./variables/variable')}
   return float(header.attrib['objectiveValue']),float(header.attrib.get('bestObjective',header.attrib['objectiveValue'])),[values.get(n,0.) for n in names]

# Backward-compatible adapter used by the deterministic-equivalent validator.
def _solve_master_interactive(model, names, mip_gap, time_limit=None, solver_threads=1):
 return _master(model,names,mip_gap,time_limit,solver_threads)

def _add(m,tidx,cidx,s,a,b,name):
 ind=[tidx[s]]; val=[1.]
 for z,v in b.items():
  if z in cidx: ind.append(cidx[z]); val.append(-v)
 m.linear_constraints.add(lin_expr=[cplex.SparsePair(ind,val)],senses=['G'],rhs=[a],names=[name])

def _checkpoint(output_dir, iteration, ub, lb, incumbent, d, timing, exact_count, nr_count, status):
 """Persist one complete Benders-iteration record before the next master solve."""
 if output_dir is None or incumbent is None: return
 out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
 first=sum(d.activation_cost(z)*v for z,v in incumbent.items())
 finite_ub=ub < float('inf'); finite_lb=lb > -float('inf')
 row={'iteration':iteration,'UB':ub if finite_ub else None,'LB':lb if finite_lb else None,'gap':(ub-lb)/max(1.,abs(ub)) if finite_ub and finite_lb else None,'incumbent_first_stage_cost':first,'incumbent_expected_recourse_cost':ub-first if finite_ub else None,'exact_benders_cuts':exact_count,'nr_cuts':nr_count,'total_cuts':exact_count+nr_count,'master_seconds':timing['master'],'exact_recourse_seconds':timing['exact_recourse'],'pareto_auxiliary_seconds':timing['pareto_auxiliary'],'nr_relaxation_seconds':timing['nr_relaxation'],'elapsed_seconds':sum(timing.values()),'status':status}
 (out/'progress.json').write_text(json.dumps(row,indent=2),encoding='utf8')
 exists=(out/'progress.csv').exists()
 with (out/'progress.csv').open('a',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=list(row));
  if not exists: w.writeheader()
  w.writerow(row)
 with (out/'row_schedule_incumbent.csv').open('w',newline='',encoding='utf8') as f:
  w=csv.writer(f); w.writerow(['arc_id','period','selected']); w.writerows((a,t,v) for (a,t),v in incumbent.items() if v>.5)

def solve_benders(d,n,scenarios,mode='BD-P',gap=1e-6,max_iter=500,benchmark=False,time_limit=None,master_time_limit=None,output_dir=None,parallel_scenarios=False,max_scenario_workers=1,solver_threads=1,nr_violation_tolerance=1e-6,**_):
 """Paper §5.5.  Exact recourse remains joint multicommodity in every iteration."""
 aliases={'plain':'BD','BD':'BD','ordinary':'BD-NR','pareto':'BD-P','BD-P':'BD-P','BD-NR':'BD-NR','BD-P-NR':'BD-P-NR'}
 if mode not in aliases: raise ValueError('mode must be BD, BD-P, BD-NR, or BD-P-NR')
 mode=aliases[mode]; use_p=mode in ('BD-P','BD-P-NR'); use_nr=mode in ('BD-NR','BD-P-NR')
 started=time.time(); cells=list(d.candidates); cidx={z:i for i,z in enumerate(cells)}; yn=[f'y_{a}_{t}' for a,t in cells]; th=[f'theta_{s}' for s in scenarios]
 m=cplex.Cplex(); [f(None) for f in (m.set_log_stream,m.set_results_stream,m.set_warning_stream,m.set_error_stream)]; m.objective.set_sense(m.objective.sense.minimize)
 m.variables.add(names=yn,obj=[d.activation_cost(z) for z in cells],types=['B']*len(cells),lb=[0.]*len(cells),ub=[1.]*len(cells)); m.variables.add(names=th,obj=[scenarios[s] for s in scenarios],lb=[0.]*len(th))
 m.linear_constraints.add(lin_expr=[cplex.SparsePair(list(range(len(cells))),[d.resource(z) for z in cells])],senses=['L'],rhs=[float(d.params['resource_budget'])])
 tidx={s:len(cells)+i for i,s in enumerate(scenarios)}; eta=.5*min(1.,float(d.params['resource_budget'])/max(1e-12,sum(d.resource(z) for z in cells))); core={z:eta for z in cells}
 exact=[]; nr=[]; timing={'master':0.,'exact_recourse':0.,'pareto_auxiliary':0.,'nr_relaxation':0.,'root_nr_generation':0.}; ordinary=pareto=fallback=aux=0
 def solve_many(schedule, relaxation=False):
  def one(s): return s,Recourse(d,n,s).solve(schedule,solver_threads=solver_threads,commodity_separable=relaxation)
  tick=time.time()
  if parallel_scenarios and len(scenarios)>1:
   with ThreadPoolExecutor(max_workers=min(max_scenario_workers,len(scenarios))) as pool: ans=list(pool.map(one,scenarios))
  else: ans=[one(s) for s in scenarios]
  timing['nr_relaxation' if relaxation else 'exact_recourse']+=time.time()-tick; return ans
 def add_nr(schedule,label,lower=None):
  added=0
  for s,r in solve_many(schedule,True):
   a,b=r['alpha'],r['beta']; rhs=a+sum(b.get(z,0.)*schedule[z] for z in cells)
   if abs(rhs-r['value'])>1e-5: raise RuntimeError(f'NR cut not tight at reference point: scenario={s}, residual={rhs-r["value"]}')
   if lower is not None and rhs<=lower[s]+nr_violation_tolerance: continue
   _add(m,tidx,cidx,s,a,b,f'nr_{label}_{s}'); nr.append({'scenario':s,'alpha':a,'beta':b,'reference_y':schedule.copy(),'value':r['value'],'type':'network_relaxation'}); added+=1
  return added
 root_before=root_after=None
 if use_nr:
  tick=time.time(); _,root_before,_=_master(m,yn+th,gap,None,solver_threads); timing['master']+=time.time()-tick
  tick=time.time(); add_nr({z:0. for z in cells},'zero'); add_nr(core,'core'); q=time.time(); _,_,x=_master(m,yn+th,gap,None,solver_threads); timing['master']+=time.time()-q; y0=dict(zip(cells,x[:len(cells)])); add_nr(y0,'preliminary',{s:x[tidx[s]] for s in scenarios}); q=time.time(); _,root_after,_=_master(m,yn+th,gap,None,solver_threads); timing['master']+=time.time()-q; timing['root_nr_generation']=time.time()-tick
 ub=float('inf'); lb=-float('inf'); incumbent=None; stopped=False; it=0
 for it in range(1,max_iter+1):
  rem=None if time_limit is None else time_limit-(time.time()-started)
  if rem is not None and rem<=0: stopped=True; break
  limit=rem if master_time_limit is None else min(rem,master_time_limit) if rem is not None else master_time_limit; tick=time.time(); _,bound,x=_master(m,yn+th,gap,limit,solver_threads); timing['master']+=time.time()-tick; lb=max(lb,bound); y=dict(zip(cells,x[:len(cells)])); solved=solve_many(y); qsum=sum(scenarios[s]*r['value'] for s,r in solved); violated=0
  for s,r in solved:
   a,b,kind=r['alpha'],r['beta'],'ordinary'
   if use_p:
    aux+=1; tick=time.time()
    try: a,b=select_pareto_cut(r,y,core); kind='pareto'; pareto+=1
    except Exception: fallback+=1
    timing['pareto_auxiliary']+=time.time()-tick
   rhs=a+sum(b.get(z,0.)*y[z] for z in cells)
   if abs(rhs-r['value'])>1e-5: raise RuntimeError(f'Exact cut not tight: scenario={s}, iteration={it}, residual={rhs-r["value"]}')
   if x[tidx[s]]<r['value']-1e-6:
    _add(m,tidx,cidx,s,a,b,f'exact_{it}_{s}'); exact.append({'scenario':s,'iteration':it,'alpha':a,'beta':b,'reference_y':y.copy(),'value':r['value'],'type':kind}); violated+=1
    if kind=='ordinary': ordinary+=1
  first=sum(d.activation_cost(z)*y[z] for z in cells); cand=first+qsum
  if cand<ub: ub=cand; incumbent=y.copy()
  _checkpoint(output_dir,it,ub,lb,incumbent,d,timing,len(exact),len(nr),'running')
  if not violated or ub-lb<=gap*max(1.,abs(ub)): break
  core={z:.7*core[z]+.3*y[z] for z in cells}
 if incumbent is None: raise RuntimeError('no incumbent')
 allocations={s:r['allocations'] for s,r in solve_many(incumbent)}; first=sum(d.activation_cost(z)*v for z,v in incumbent.items()); status='time_limit' if stopped else ('converged' if ub-lb<=gap*max(1.,abs(ub)) else 'iteration_limit')
 _checkpoint(output_dir,it,ub,lb,incumbent,d,timing,len(exact),len(nr),status)
 return {'method':mode,'objective':ub,'first_stage':first,'expected_recourse':ub-first,'LB':lb,'UB':ub,'gap':(ub-lb)/max(1.,abs(ub)),'iterations':it,'cuts':len(exact)+len(nr),'exact_benders_cuts':len(exact),'nr_cuts':len(nr),'ordinary_cuts':ordinary,'pareto_cuts':pareto,'fallback_cuts':fallback,'pareto_auxiliary_lps':aux,'initial_master_bound_before_nr':root_before,'root_bound_after_nr':root_after,'root_bound_improvement':None if root_before is None else root_after-root_before,'timing_seconds':timing,'y':incumbent,'scenario_allocations':allocations,'seconds':time.time()-started,'stopped_by_time_limit':stopped,'termination_reason':status,'parallel_scenarios':parallel_scenarios,'scenario_workers':min(max_scenario_workers,len(scenarios)) if parallel_scenarios else 1,'solver_threads_per_model':solver_threads,'cut_records':exact,'nr_cut_records':nr}
