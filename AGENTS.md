# AGENTS.md

## Project Layout

- Repository root: `C:\faq_work\Papers\ROW`
- Python project: `ROW-Design`
- Input workbooks: `数据\*.xlsx`
- Main package source: `ROW-Design\src\row`
- Main CLI entry: `python -m row.cli`
- Batch comparison script: `ROW-Design\run_experiment.py`

## Environment

Use the project-specific Conda environment `row-design-cplex221`. Do not install
project packages or environment variables into the shared `cplex310`
environment.

```powershell
conda activate row-design-cplex221
cd C:\faq_work\Papers\ROW\ROW-Design
```

The checked-in `.venv` is not the default runtime. It points to an old machine-specific Python 3.14 path and should be ignored unless it is deliberately rebuilt.

Installed runtime components in `row-design-cplex221`:

- Python 3.10.21
- editable project install: `night-row`
- `openpyxl`
- IBM CPLEX Python API 22.1 from CPLEX Studio 22.1
- `pytest`

## CPLEX

The pip `cplex` wheel can run as Community Edition and exceed size limits on real ROW instances. This machine has IBM CPLEX Studio 22.1 installed at:

```powershell
C:\Program Files\IBM\ILOG\CPLEX_Studio221
```

The `row-design-cplex221` Conda environment is an isolated clone of the
licensed Studio 22.1 runtime and has `CPLEX_INTERACTIVE` configured to use:

```powershell
C:\Program Files\IBM\ILOG\CPLEX_Studio221\cplex\bin\x64_win64\cplex.exe
```

Without this, larger models may fail with CPLEX error 1016.

The same environment also has `PYTHONNOUSERSITE=1` configured so it does not accidentally import packages from the user's global Python site-packages.

## Common Commands

Run CLI help:

```powershell
conda run -n row-design-cplex221 python -m row.cli --help
```

Run a small validated smoke instance:

```powershell
cd C:\faq_work\Papers\ROW\ROW-Design
conda run -n row-design-cplex221 python -m row.cli ..\数据\R04_ROW_H1_M10.xlsx --instance R04_Y1_S10_H1_M10 --config configs\extensive_smoke.json --out results\cplex221_smoke --skip-cut-audit
```

Run the default experiment pattern:

```powershell
cd C:\faq_work\Papers\ROW\ROW-Design
conda run -n row-design-cplex221 python -m row.cli ..\数据\R04_ROW_H1_M10.xlsx --instance R04_Y1_S30_H1_M10 --config configs\default_experiment.json --out results\run_name
```

Run tests:

```powershell
cd C:\faq_work\Papers\ROW\ROW-Design
conda run -n row-design-cplex221 python -m pytest -q
```

## Known Configuration Notes

- `configs\default_experiment.json`, `configs\extensive_smoke.json`, `configs\r04_s10_pareto_nr_3600s.json`, and `configs\r04_s10_plain_benders_5min.json` currently load with `src\row\config.py`.
- Several archived configs contain obsolete keys such as `dual_greedy_warm_start`, `root_lp_cut_rounds`, or `cutset`; they will fail unless the config loader is updated.
- Workbook instance IDs include values such as `R04_Y1_S10_H1_M10`, `R04_Y1_S30_H1_M10`, `R10_Y1_S30_H1_M10`, and `Sioux_Falls_30OD_Y1_S30_H1_M10`.

## Working Rules

- Do not use `ROW-Design\.venv` as the default runtime.
- Do not run repository archive files (`*.rar`) as source.
- Prefer direct Python commands above over ad hoc wrapper scripts unless a task explicitly asks for a wrapper.
- Generated outputs go under `ROW-Design\results\...`.
