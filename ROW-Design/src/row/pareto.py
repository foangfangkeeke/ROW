from __future__ import annotations
import cplex

def select_pareto_cut(base, yhat, ycore, tol=1e-6):
 """Solve Magnanti-Wong's auxiliary dual on the optimal face at ``yhat``.

``base`` is a solved recourse LP whose row metadata expresses every RHS as
``constant + coefficient * y``.  It returns a dual-derived affine cut, or
raises so the caller can use the ordinary optimal dual as the required fallback.
"""
 primal=base.get('model')
 if primal is None: raise RuntimeError('Pareto auxiliary requires an in-process CPLEX LP model')
 rows=primal.linear_constraints.get_rows(); senses=primal.linear_constraints.get_senses(); costs=primal.objective.get_linear()
 meta=base['meta']; qhat=base['value']; nr=len(rows); dual=cplex.Cplex()
 dual.set_log_stream(None);dual.set_results_stream(None);dual.set_warning_stream(None);dual.set_error_stream(None);dual.objective.set_sense(dual.objective.sense.maximize)
 rhs_hat=[];rhs_core=[]
 for kind,b,coef in meta:
  rhs_hat.append(b+sum(v*yhat.get(cell,0.) for cell,v in coef.items()))
  rhs_core.append(b+sum(v*ycore.get(cell,0.) for cell,v in coef.items()))
 lb=[-cplex.infinity if s=='E' else -cplex.infinity for s in senses]
 ub=[cplex.infinity if s=='E' else 0. for s in senses]
 dual.variables.add(names=[f'pi_{i}' for i in range(nr)],obj=rhs_core,lb=lb,ub=ub)
 # W^T pi <= q
 by_col=[[] for _ in costs]
 for i,row in enumerate(rows):
  for j,v in zip(row.ind,row.val): by_col[j].append((i,v))
 dual.linear_constraints.add(lin_expr=[cplex.SparsePair([i for i,_ in col],[v for _,v in col]) for col in by_col],senses=['L']*len(costs),rhs=costs)
 # Restrict to the dual optimal face at yhat.
 dual.linear_constraints.add(lin_expr=[cplex.SparsePair(list(range(nr)),rhs_hat)],senses=['E'],rhs=[qhat])
 dual.solve()
 if dual.solution.get_status() not in (1,101,102): raise RuntimeError('Pareto auxiliary status: '+dual.solution.get_status_string())
 pi=dual.solution.get_values(); alpha=0.;beta={}
 for value,(kind,b,coef) in zip(pi,meta):
  alpha+=value*b
  for cell,v in coef.items(): beta[cell]=beta.get(cell,0.)+value*v
 residual=abs(qhat-(alpha+sum(beta.get(cell,0.)*yhat.get(cell,0.) for cell in yhat)))
 if residual>tol: raise RuntimeError(f'Pareto cut is not tight: {residual}')
 return alpha,beta
