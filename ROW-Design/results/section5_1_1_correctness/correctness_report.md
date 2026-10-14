# 5.1.1 Correctness Check

Rows passed: 11/11

## Cases

- Toy three-binary enumeration reference: 8.0000000000
- R04 reduced single-scenario reference: 34642.2666503903; instance=R04_Y1_S10_H1_M10; scenario=1; candidate_count=6/360

## Results

| Case | Method | Objective | Abs diff | Gap | Iterations | Pass |
|---|---:|---:|---:|---:|---:|---:|
| toy_three_binary | enumeration | 8.0000000000 | 0 | 0 | 1 | True |
| toy_three_binary | extensive_form | 8.0000000000 | 1.78e-15 | 0 | 1 | True |
| toy_three_binary | BD | 8.0000000000 | 0 | 2.22e-16 | 3 | True |
| toy_three_binary | BD-P | 8.0000000000 | 0 | 2.22e-16 | 3 | True |
| toy_three_binary | BD-NR | 8.0000000000 | 0 | 2.22e-16 | 1 | True |
| toy_three_binary | BD-P-NR | 8.0000000000 | 0 | 2.22e-16 | 1 | True |
| r04_reduced_single_scenario | extensive_form | 34642.2666503903 | 0 | -8.4e-16 | 1 | True |
| r04_reduced_single_scenario | BD | 34642.2666503903 | 1.46e-11 | -1.05e-15 | 2 | True |
| r04_reduced_single_scenario | BD-P | 34642.2666503903 | 1.46e-11 | -1.47e-15 | 2 | True |
| r04_reduced_single_scenario | BD-NR | 34642.2666503903 | 1.46e-11 | -1.05e-15 | 2 | True |
| r04_reduced_single_scenario | BD-P-NR | 34642.2666503903 | 1.46e-11 | -1.47e-15 | 2 | True |
