| Workload | Concurrency | Requests | Output tok/s | TTFT p50 / p90 (ms) | ITL p50 / p99 (ms) | Prefix reuse in trace | Server prefix-cache hit rate | Peak KV-cache use | Preemptions |
|---|---|---|---|---|---|---|---|---|---|
| prefix-cache-on/full | 1 | 48 | 20.0 | 206 / 710 | 27.5 / 41.7 | 94% | 93% | 10% | 0 |
| prefix-cache-on/full | 2 | 68 | 36.0 | 88 / 235 | 31.9 / 48.6 | 93% | 98% | 11% | 0 |
| prefix-cache-on/full | 4 | 149 | 19.5 | 322 / 2,188 | 62.7 / 669.8 | 92% | 94% | 47% | 0 |
| prefix-cache-on/full | 8 | 350 | 43.8 | 441 / 1,074 | 84.4 / 691.1 | 93% | 97% | 58% | 0 |
| prefix-cache-on/truncate | 1 | 60 | 22.9 | 270 / 533 | 28.4 / 42.0 | 94% | 94% | 10% | 0 |
| prefix-cache-on/truncate | 2 | 98 | 35.5 | 123 / 327 | 33.2 / 50.7 | 94% | 98% | 13% | 0 |
| prefix-cache-on/truncate | 4 | 180 | 31.7 | 214 / 1,782 | 51.7 / 191.6 | 94% | 96% | 24% | 0 |
| prefix-cache-on/truncate | 8 | 385 | 54.9 | 354 / 664 | 75.3 / 415.3 | 94% | 97% | 55% | 0 |
| prefix-cache-on/rolling | 1 | 48 | 24.2 | 372 / 713 | 26.3 / 32.0 | 71% | 71% | 4% | 0 |
| prefix-cache-on/rolling | 2 | 70 | 49.0 | 85 / 353 | 28.0 / 40.2 | 70% | 91% | 6% | 0 |
| prefix-cache-on/rolling | 4 | 180 | 25.3 | 399 / 1,896 | 35.1 / 1445.1 | 59% | 66% | 19% | 0 |
| prefix-cache-on/rolling | 8 | 383 | 36.9 | 772 / 1,677 | 58.6 / 2433.2 | 65% | 65% | 24% | 0 |
