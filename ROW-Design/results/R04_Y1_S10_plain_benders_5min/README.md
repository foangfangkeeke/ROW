# R04_Y1, S10 — plain Benders baseline, five-minute limit

This run uses ordinary exact Benders optimality cuts only.  It does not use Pareto cuts or root-only network-relaxation (NR) cuts.  `progress.json` is the terminal record at the 300-second algorithm limit; `comparison_with_section5_5min.csv` compares it with the prior Section-5 strategies under the same S10 / five-minute setup.

The process completed the Benders algorithm at the time limit.  Its original post-solve reporting then encountered a tuple-key JSON serialization error, so no scenario reports were produced by that invocation.  The saved terminal progress and incumbent schedule are unaffected.
