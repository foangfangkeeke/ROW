"""Run the three Section-5 Benders variants on exactly the same instance/scenarios."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from row.data import load_excel, audit_report
from row.network import build_network
from row.reduction import reduce_network
from row.benders import solve_benders
from row.validation import cut_audit
from row.config import ExperimentConfig

def main():
 p=argparse.ArgumentParser(); p.add_argument('excel'); p.add_argument('--instance'); p.add_argument('--methods',nargs='+',default=['BD','BD-P','BD-P-NR']); p.add_argument('--output',default='results'); p.add_argument('--scenarios',default='S30'); p.add_argument('--time-limit',type=float); p.add_argument('--master-time-limit',type=float); p.add_argument('--mip-gap',type=float,default=.01); p.add_argument('--seed',type=int,default=7); p.add_argument('--audit-cuts',action='store_true')
 a=p.parse_args(); allowed={'BD','BD-P','BD-P-NR'}
 if set(a.methods)-allowed: raise ValueError('methods must be BD, BD-P, and/or BD-P-NR')
 out=Path(a.output); out.mkdir(parents=True,exist_ok=True); d=load_excel(a.excel,a.instance); n=build_network(d); n,red=reduce_network(d,n); (out/'audit.txt').write_text(audit_report(d),encoding='utf8'); (out/'reduction.json').write_text(json.dumps(red,indent=2),encoding='utf8')
 rows=[]
 for method in a.methods:
  md=out/method; md.mkdir(exist_ok=True)
  result=solve_benders(d,n,d.probabilities[a.scenarios],mode=method,gap=a.mip_gap,time_limit=a.time_limit,master_time_limit=a.master_time_limit,output_dir=md,parallel_scenarios=True,max_scenario_workers=4,solver_threads=1)
  summary={k:v for k,v in result.items() if k not in ('y','cut_records','nr_cut_records','scenario_allocations')}; summary.update({'instance':a.instance,'number_of_scenarios':len(d.probabilities[a.scenarios]),'seed':a.seed,'cut_audit':'not_requested'})
  (md/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
  if a.audit_cuts:
   failures=cut_audit(d,n,d.probabilities[a.scenarios],result['cut_records'])+cut_audit(d,n,d.probabilities[a.scenarios],result['nr_cut_records'],relaxation=True)
   if failures: raise RuntimeError(json.dumps(failures[0],default=str))
   summary['cut_audit']='passed'; (md/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
  rows.append(summary)
 fields=sorted({k for row in rows for k in row if not isinstance(row[k],(dict,list))})
 with (out/'comparison.csv').open('w',newline='',encoding='utf8') as f: w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:v for k,v in r.items() if k in fields} for r in rows])
if __name__=='__main__': main()
