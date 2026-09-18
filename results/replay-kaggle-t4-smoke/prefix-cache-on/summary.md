| Workload | Concurrency | Requests | Output tok/s | TTFT p50 / p90 (ms) | ITL p50 / p99 (ms) | Prefix reuse in trace | Server prefix-cache hit rate | Peak KV-cache use | Preemptions |
|---|---|---|---|---|---|---|---|---|---|
| prefix-cache-on/full | 1 | 30 | 19.1 | 197 / 259 | 30.2 / 38.4 | 95% | 94% | 6% | 0 |
| prefix-cache-on/full | 2 | 44 | 31.5 | 85 / 266 | 30.7 / 41.9 | 94% | 98% | 6% | 0 |
