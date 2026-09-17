from __future__ import annotations
import argparse, csv, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .config import load_config
from .data import load_excel, audit_report
from .network import build_network
from .reduction import reduce_network
from .benders import solve_benders
from .validation import cut_audit, scenario_diagnostics

def main():
 p=argparse.ArgumentParser(description='Nighttime ROW experiments')
 p.add_argument('excel'); p.add_argument('--config',help='JSON experiment configuration')
 p.add_argument('--out',default='results'); p.add_argument('--instance',help='Workbook Instance_Index identifier, e.g. R10_Y1_S30'); p.add_argument('--skip-cut-audit',action='store_true')
 a=p.parse_args(); cfg=load_config(a.config); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
 d=load_excel(a.excel,a.instance or cfg.instance_id); n=build_network(d,cfg.reductions); n,reduction_stats=reduce_network(d,n,cfg.reductions); (out/'audit.txt').write_text(audit_report(d),encoding='utf8'); (out/'reduction.json').write_text(json.dumps(reduction_stats,indent=2),encoding='utf8')
 algorithm=cfg.algorithm
 if algorithm=='plain': algorithm='BD'
 if algorithm=='ordinary':
  algorithm='BD-P-NR' if cfg.cuts.pareto and cfg.cuts.network_relaxation else ('BD-P' if cfg.cuts.pareto else 'BD-NR')
 if algorithm=='pareto': algorithm='BD-P'
 if algorithm=='extensive':
  from .extensive_form import solve_extensive
  result=solve_extensive(d,n,d.probabilities[cfg.scenario_set],gap=cfg.master_mip_gap,time_limit=cfg.time_limit_seconds,solver_threads=cfg.solver_threads)
 else:
  result=solve_benders(d,n,d.probabilities[cfg.scenario_set],mode=algorithm,gap=cfg.master_mip_gap,max_iter=cfg.max_benders_iterations,time_limit=cfg.time_limit_seconds,master_time_limit=cfg.master_time_limit_seconds,output_dir=out,parallel_scenarios=cfg.parallel_scenarios,max_scenario_workers=cfg.max_scenario_workers,solver_threads=cfg.solver_threads,nr_violation_tolerance=cfg.nr_violation_tolerance)
 if result['cut_records']:
  cut_report=[{**{k:v for k,v in r.items() if k not in ('beta','reference_y')},'beta':[{'arc_id':cell[0],'period':cell[1],'coefficient':v} for cell,v in r['beta'].items()]} for r in result['cut_records']+result.get('nr_cut_records',[])]
  (out/'benders_cuts.json').write_text(json.dumps(cut_report,indent=2),encoding='utf8')
 failures=[] if (a.skip_cut_audit or not cfg.cut_audit) else cut_audit(d,n,d.probabilities[cfg.scenario_set],result['cut_records'])+cut_audit(d,n,d.probabilities[cfg.scenario_set],result.get('nr_cut_records',[]),relaxation=True)
 if 'scenario_allocations' in result: (out/'scenario_allocations.json').write_text(json.dumps(result['scenario_allocations'],indent=2),encoding='utf8')
 scenario_ids=list(d.probabilities[cfg.scenario_set])
 if cfg.parallel_scenarios and len(scenario_ids)>1:
  with ThreadPoolExecutor(max_workers=min(cfg.max_scenario_workers,len(scenario_ids))) as pool:
   diagnostics=list(pool.map(lambda s:scenario_diagnostics(d,n,s,result['y']),scenario_ids))
 else:
  diagnostics=[scenario_diagnostics(d,n,s,result['y']) for s in scenario_ids]
 (out/'capacity_residuals.json').write_text(json.dumps([{ 'scenario':x['scenario'],'residuals':x['capacity_residuals']} for x in diagnostics],indent=2),encoding='utf8')
 for x in diagnostics: x.pop('capacity_residuals',None)
 (out/'scenario_diagnostics.json').write_text(json.dumps(diagnostics,indent=2),encoding='utf8')
 shares={'A':0.,'H':0.,'E':0.,'demand':0.}
 for s,p in d.probabilities[cfg.scenario_set].items():
  alloc=next(x['allocations'] for x in diagnostics if x['scenario']==s)
  if alloc is not None:
   for k,v in alloc.items():
    shares['demand']+=p*d.demand[s,k]
    for mode in ('A','H','E'): shares[mode]+=p*v[mode]
 resource=sum(d.resource(cell)*v for cell,v in result['y'].items())
 summary={k:v for k,v in result.items() if k not in ('y','cut_records','scenario_allocations')}; summary.update({'resolved_algorithm':algorithm,'recourse_solver_backends':sorted({x['backend'] for x in diagnostics}),'ROW_resource_usage':resource,'mode_shares':{m:(shares[m]/shares['demand'] if shares['demand'] else None) for m in ('A','H','E')},'config':cfg.to_dict(),'cut_audit':'skipped' if (a.skip_cut_audit or not cfg.cut_audit) else 'passed'})
 (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
 with (out/'row_schedule.csv').open('w',newline='',encoding='utf8') as f:
  w=csv.writer(f);w.writerow(['arc_id','period','selected']);w.writerows((x[0],x[1],v) for x,v in result['y'].items() if v>.5)
 if failures: raise SystemExit(f'cut audit failed: {failures[:3]}')
 print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
