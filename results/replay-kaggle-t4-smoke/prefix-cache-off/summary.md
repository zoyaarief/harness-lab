| Workload | Concurrency | Requests | Output tok/s | TTFT p50 / p90 (ms) | ITL p50 / p99 (ms) | Prefix reuse in trace | Server prefix-cache hit rate | Peak KV-cache use | Preemptions |
|---|---|---|---|---|---|---|---|---|---|
| prefix-cache-off/full | 1 | 30 | 10.5 | 1,695 / 3,860 | 31.1 / 40.0 | 95% | – | 6% | 0 |
| prefix-cache-off/full | 2 | 44 | 14.9 | 1,562 / 3,687 | 33.3 / 435.0 | 94% | – | 7% | 0 |
