# 5.1.2 Cut Effectiveness 结果阅读说明

这个目录是 5.1.2 的全量运行结果，已经覆盖当前摘要里要求的 24 组实验：

- 8 个算例：R04-R10 和 Sioux_Falls_30OD。
- 3 种算法：BD、BD-P、BD-P-NR。
- 总组数：`8 * 3 = 24`。

## 复现命令

在 `ROW-Design` 目录运行。单独的输出目录不会覆盖已提交结果。

```powershell
conda run -n row-design-cplex221 python tools\run_5_1_2_cut_effectiveness.py `
  --instances R04 R05 R06 R07 R08 R09 R10 Sioux_Falls_30OD `
  --methods BD BD-P BD-P-NR --scenario-set S10 `
  --mip-gap 0.01 --time-limit 7200 --master-time-limit 600 --max-iter 500 `
  --max-scenario-workers 4 --solver-threads 1 --parallel-scenarios `
  --out results\reproduced\section5_1_2_cut_effectiveness
```

## 先看结论

当前结果已经有论文 5.1.2 表格需要的信息。最重要的入口文件是：

| 文件 | 用途 |
|---|---|
| `aggregate.csv` | 最适合导入 Excel、Python 或论文表格的总表。每行是一组实验。 |
| `report.md` | 人可直接阅读的 Markdown 总表，适合快速检查结果。 |
| `analysis.md` | 当前结果的初步解释，包括收敛数量、速度模式和主要结论。 |
| `aggregate.json` | 和 `aggregate.csv` 对应的结构化版本，适合程序继续处理。 |

如果只想判断 5.1.2 是否已经跑全，读 `report.md` 和 `aggregate.csv` 即可。

## 是否满足摘要里的需求

摘要要求的 5.1.2 指标在 `aggregate.csv` 中都有对应列：

| 摘要要求 | `aggregate.csv` 字段 |
|---|---|
| Solution time | `solution_time_seconds` |
| Benders iterations | `benders_iterations` |
| Final gap | `reported_gap`，同时保留 `signed_gap` |
| Cut-generation time | `cut_generation_seconds` |
| LB | `LB` |
| UB | `UB` |
| Pareto cuts 数量 | `pareto_cuts` |
| NR cuts 数量 | `nr_cuts` |

建议论文表格主字段使用 `reported_gap`。`signed_gap` 主要用于诊断上下界方向或异常情况。

## 当前完整性检查

`aggregate.csv` 当前有 24 行：

| 维度 | 当前结果 |
|---|---|
| 总运行数 | 24 |
| 算例 | R04、R05、R06、R07、R08、R09、R10、Sioux_Falls_30OD |
| 方法 | BD、BD-P、BD-P-NR |
| 每个算例方法数 | 3 |
| BD-P / BD-P-NR 的 Pareto 状态 | 全部为 `active` |
| Pareto fallback | 0 |

这说明 5.1.2 的组合已经跑全，且 BD-P 和 BD-P-NR 没有退回到普通 cut。

## 怎么读总表

建议按这个顺序读：

1. 先看 `termination_reason`。
   - `converged` 表示在 1% gap 口径下收敛。
   - `time_limit` 表示触发 7200 秒总时间上限。

2. 再看 `solution_time_seconds` 和 `benders_iterations`。
   - 如果两个方法都收敛，直接比较求解时间和迭代数。
   - 如果一个方法超时，另一个方法收敛，收敛方法明显更强。
   - 如果两个都超时，就不要只比较时间，因为都接近 7200 秒；这时主要比较 `reported_gap`、`LB`、`UB`。

3. 再看 cut 代价和 cut 数量。
   - `cut_generation_seconds` 是生成加强 cut 的总开销。
   - `pareto_cuts` 记录 Pareto cut 数量。
   - `nr_cuts` 记录 network-relaxation cut 数量。
   - BD 的这些字段应为 0 或不适用。

4. 最后看诊断字段。
   - `pareto_status=active` 表示 Pareto cut 正常生效。
   - `fallback_cuts=0` 表示没有因为 Pareto 辅助问题失败而退回普通 cut。
   - `pareto_auxiliary_lps` 可以理解为求解 Pareto 辅助 LP 的次数。

## 当前主要结果

从当前 `report.md` 看：

| 方法 | 收敛数 | 超时数 | 直接解读 |
|---|---:|---:|---|
| BD | 1 | 7 | 只有 R04 收敛，普通 Benders cut 在这批算例上偏弱。 |
| BD-P | 5 | 3 | 对 R04、R06、R07、R08、R09 明显加速并收敛。 |
| BD-P-NR | 5 | 3 | 也收敛 5 个算例，但 NR 的额外开销使总时间不总是优于 BD-P。 |

比较时需要注意：

- R04、R06、R07、R08、R09 是最能支持 cut 有效性的实例，因为 BD-P/BD-P-NR 能在 1% gap 内收敛，而 BD 多数超时。
- R05、R10、Sioux_Falls_30OD 是困难实例，三种方法至少有强方法超时，应主要比较最终 gap 和上下界改善。
- Sioux_Falls_30OD 的 gap 仍然很大，只能说明加强 cut 有改善，但不能说明该设置下已经稳定求解该大实例。

## 子目录怎么看

每个算例目录结构类似：

```text
R04/
  audit.txt
  reduction.json
  BD/
    progress.csv
    progress.json
    row_schedule_incumbent.csv
    summary.json
  BD-P/
    ...
  BD-P-NR/
    ...
```

子目录文件用途：

| 文件 | 用途 |
|---|---|
| `summary.json` | 单次运行的最终结果，`aggregate.csv` 就是从这些文件汇总来的。 |
| `progress.csv` / `progress.json` | 迭代过程记录，用于画收敛曲线或诊断某次运行。 |
| `row_schedule_incumbent.csv` | 当前最好解对应的 ROW 开放方案，5.1.2 主表一般不需要。 |
| `audit.txt` | 算例级数据检查信息。 |
| `reduction.json` | 网络规模和预处理信息。 |

## 缺什么

当前 5.1.2 主表信息不缺。唯一没有默认保存的是逐条 Benders cut 明细 `benders_cuts.json`，因为全量运行默认没有加 `--save-cuts`。这不影响摘要要求的 5.1.2 指标；只有在需要诊断每一条 cut 的系数、场景来源或违反程度时，才需要重跑并加 `--save-cuts`。

## 推荐写法

论文里可以把 5.1.2 的主结论写成：

- Pareto-oriented exact cuts 显著减少 Benders 迭代并提升收敛表现。
- BD-P 在 8 个算例中有 5 个达到 1% gap，而 plain BD 只有 1 个达到。
- NR cuts 提供额外强化，但在当前实现和参数下，其额外生成成本使 BD-P-NR 不总是比 BD-P 更快。
- 对 R05、R10 和 Sioux_Falls_30OD，结果应按 time-limit case 报告最终 gap、LB 和 UB，而不是仅比较 wall-clock time。
- Data note: `aggregate.csv` has 24 rows for 8 networks times 3 methods. Required table fields are present: `objective`, `UB`, `LB`, `reported_gap`, `solution_time_seconds`, `benders_iterations`, cut counts, and termination fields. Run-level `summary.json`, `progress.csv`, `progress.json`, and `row_schedule_incumbent.csv` are present under each network/method directory.
