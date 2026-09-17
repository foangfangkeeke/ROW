from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
@dataclass
class ReductionOptions:
    R1_shortest_time: bool=True; R2_reachability: bool=True; R3_budget_paths: bool=True
    # Retained only so archived pre-9.16 JSON files remain readable.  The
    # current manuscript has no R4 candidate-elimination rule.
    R4_unused_cells: bool=False
@dataclass
class CutOptions:
    ordinary: bool=True; pareto: bool=False; network_relaxation: bool=False
@dataclass
class ExperimentConfig:
    instance_id: str|None=None; scenario_set: str='S10'; algorithm: str='ordinary'; master_mip_gap: float=1e-6
    time_limit_seconds: float|None=None; master_time_limit_seconds: float|None=None; max_benders_iterations: int=500; cut_audit: bool=True
    parallel_scenarios: bool=False; max_scenario_workers: int=1; solver_threads: int=1
    nr_violation_tolerance: float=1e-6
    reductions: ReductionOptions=field(default_factory=ReductionOptions)
    cuts: CutOptions=field(default_factory=CutOptions)
    def to_dict(self): return asdict(self)
def load_config(path: str|Path|None=None) -> ExperimentConfig:
    if path is None: return ExperimentConfig()
    raw=json.loads(Path(path).read_text(encoding='utf8')); cfg=ExperimentConfig()
    for k,v in raw.items():
        if k=='reductions': cfg.reductions=ReductionOptions(**v)
        elif k=='cuts': cfg.cuts=CutOptions(**v)
        elif hasattr(cfg,k): setattr(cfg,k,v)
        else: raise ValueError(f'Unknown experiment configuration key: {k}')
    if cfg.algorithm not in ('BD','BD-P','BD-NR','BD-P-NR','plain','ordinary','pareto','extensive'): raise ValueError('algorithm must be BD, BD-P, BD-NR, BD-P-NR, or extensive')
    if cfg.master_mip_gap<=0: raise ValueError('master_mip_gap must be positive')
    if cfg.master_time_limit_seconds is not None and cfg.master_time_limit_seconds<=0: raise ValueError('master_time_limit_seconds must be positive')
    if cfg.max_scenario_workers<1 or cfg.solver_threads<1: raise ValueError('worker and solver thread counts must be positive')
    if cfg.nr_violation_tolerance<=0: raise ValueError('nr_violation_tolerance must be positive')
    return cfg
