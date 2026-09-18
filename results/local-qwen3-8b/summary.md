| Variant | Pass rate (95% CI) | Median steps | Prompt tok / task | Prefill computed / task | Cache hit | Output tok / task | TTFT p50 / p90 | Median task time |
|---|---|---|---|---|---|---|---|---|
| full | 1/24 = 4% (1%–20%) | 30 | 112,174 | 7,085 | 94% | 1,051 | 3.3 s / 7.7 s | 246 s |
| truncate | 2/24 = 8% (2%–26%) | 30 | 99,241 | 6,027 | 94% | 1,184 | 2.6 s / 6.7 s | 163 s |
| rolling | 0/24 = 0% (0%–14%) | 30 | 57,695 | 20,481 | 65% | 1,058 | 7.3 s / 11.8 s | 283 s |
| compaction | 2/24 = 8% (2%–26%) | 30 | 100,844 | 9,715 | 90% | 1,198 | 2.5 s / 5.0 s | 161 s |
| no-repeat-guard | 1/24 = 4% (1%–20%) | 30 | 77,551 | 6,398 | 92% | 1,060 | 2.1 s / 4.2 s | 146 s |
| bash-only | 0/24 = 0% (0%–14%) | 30 | 111,594 | 6,652 | 94% | 1,050 | 2.1 s / 4.0 s | 115 s |

Paired difference in pass rate vs `full` (same tasks; bootstrap 95% CI over tasks):

- `truncate`: +4% (+0% to +12%), 12 tasks
- `rolling`: -4% (-12% to +0%), 12 tasks
- `compaction`: +4% (+0% to +12%), 12 tasks
- `no-repeat-guard`: +0% (-12% to +12%), 12 tasks
- `bash-only`: -4% (-12% to +0%), 12 tasks

2 trial(s) were interrupted by system sleep; they count toward pass rates and token totals but are excluded from all timing columns and charts.

Stop reasons:

| variant         |   context_limit |   max_steps |   submitted |
|:----------------|----------------:|------------:|------------:|
| bash-only       |               0 |          22 |           2 |
| compaction      |               0 |          14 |          10 |
| full            |               1 |          16 |           7 |
| no-repeat-guard |               2 |          13 |           9 |
| rolling         |               0 |          16 |           8 |
| truncate        |               0 |          18 |           6 |
