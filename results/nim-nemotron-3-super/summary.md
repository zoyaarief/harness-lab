| Variant | Pass rate (95% CI) | Median steps | Prompt tok / task | Prefill computed / task | Cache hit | Output tok / task | TTFT p50 / p90 | Median task time |
|---|---|---|---|---|---|---|---|---|
| full | 10/12 = 83% (55%–95%) | 22 | 95,681 | 84,065 | 12% | 12,582 | 0.6 s / 1.2 s | 141 s |
| truncate | 12/12 = 100% (76%–100%) | 17 | 60,472 | 59,768 | 1% | 9,930 | 0.6 s / 1.4 s | 139 s |
| rolling | 11/12 = 92% (65%–99%) | 30 | 70,414 | 70,414 | 0% | 12,506 | 0.6 s / 1.2 s | 229 s |
| compaction | 11/12 = 92% (65%–99%) | 14 | 51,995 | 51,995 | 0% | 8,725 | 0.6 s / 1.1 s | 125 s |

Paired difference in pass rate vs `full` (same tasks; bootstrap 95% CI over tasks):

- `truncate`: +17% (+0% to +42%), 12 tasks
- `rolling`: +8% (+0% to +25%), 12 tasks
- `compaction`: +8% (+0% to +25%), 12 tasks

Stop reasons:

| variant    |   format_errors |   max_steps |   submitted |
|:-----------|----------------:|------------:|------------:|
| compaction |               0 |           1 |          11 |
| full       |               0 |           1 |          11 |
| rolling    |               1 |           7 |           4 |
| truncate   |               0 |           0 |          12 |
