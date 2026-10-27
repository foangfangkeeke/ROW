# Nighttime ROW stochastic design

The implementation follows the September 16 paper Section 5. The comparison methods are BD (ordinary optimal-dual cuts), BD-P (Pareto-oriented exact cuts), and BD-P-NR (Pareto cuts plus root-only commodity-separable network-relaxation cuts). Exact recourse is the joint multicommodity LP; NR is a lower-bounding relaxation.

## CPLEX 22.2 environment

The original Section 5 results used CPLEX Studio 22.1 with Python 3.10.21. The following is a separate **CPLEX 22.2.0.1 / Python 3.12** environment; it does not replace the original environment. IBM publishes CPLEX 22.2.0.1 wheels for Python 3.10–3.14 on Windows x86-64, including Python 3.12. Wheel availability differs by platform. See [CPLEX on PyPI](https://pypi.org/project/cplex/22.2.0.1/).

From this directory, on a machine with Conda:

```powershell
conda env create -f environment-cplex222.yml
conda activate row-design-cplex222
python -m pip install --no-deps -e .
python -c "import sys, cplex, openpyxl; print(sys.version); print('CPLEX', cplex.Cplex().get_version()); print('openpyxl', openpyxl.__version__); print('CPLEX module', cplex.__file__)"
python -m row.cli --help
python -m pytest -q
```

The environment file installs the PyPI CPLEX Community Edition API. It is sufficient for the micro tests, but **not for all project instances**: the R04 check below exceeds its size limit (error 1016). For full experiments, use a properly licensed CPLEX 22.2 Python API/runtime following the IBM installation instructions for your platform; check `cplex.__file__` and `cplex.Cplex().get_version()` to confirm which API is loaded. Install the licensed API into the dedicated environment without allowing a subsequent pip command to replace it with the Community Edition package.

For code paths that fall back to the Interactive Optimizer after error 1016, set `CPLEX_INTERACTIVE` to the actual licensed executable. Example for the default Windows installation, if present:

```powershell
$env:CPLEX_INTERACTIVE = 'C:\Program Files\IBM\ILOG\CPLEX_Studio222\cplex\bin\x64_win64\cplex.exe'
$env:PYTHONNOUSERSITE = '1'
```

This fallback is not implemented for every CPLEX operation, so it is not a substitute for verifying the licensed Python API and the complete experiment. Do not use the checked-in `.venv`; it refers to an old machine.

Check the small correctness experiment using the licensed environment:

```powershell
python tools\run_5_1_1_correctness.py --instance R04_Y1_S10_H1_M10 --scenario 1 --candidate-count 6 --tol 1e-6 --time-limit 120 --master-time-limit 60 --max-iter 50 --solver-threads 1 --out results\reproduced\cplex222_5_1_1
```

Compare `comparison.csv` with `results/section5_1_1_correctness/comparison.csv`. On Linux with Python 3.12.14 and CPLEX Community Edition 22.2.0.1, the CLI and six micro tests passed; two workbook-dependent regression tests were skipped, and the R04 correctness run failed at the Community Edition limit. Full licensed 22.2 experiments and Windows installation remain to be verified.

## Section 5 results and reproduction

Inputs are in `../数据/`, and experiment scripts are under `tools/`. See the README in each `results/section5_*` directory for its commands, settings and results. Use a separate output directory for reruns; record the actual Python, CPLEX, OS and hardware versions. The committed results were obtained with 22.1, so solver version and hardware changes may change elapsed time and time-limited bounds.

The three exact reductions R1–R3 screen individual time-space nodes, retain source-to-sink reachable states, and prune budget-infeasible autonomous arcs. The ROW candidate set is not reduced.
