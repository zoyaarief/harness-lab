| Workload | Concurrency | Requests | Output tok/s | TTFT p50 / p90 (ms) | ITL p50 / p99 (ms) | Prefix reuse in trace | Server prefix-cache hit rate | Peak KV-cache use | Preemptions |
|---|---|---|---|---|---|---|---|---|---|
| prefix-cache-off/full | 1 | 48 | 8.7 | 1,734 / 7,502 | 27.6 / 42.6 | 94% | – | 10% | 0 |
| prefix-cache-off/full | 2 | 68 | 11.8 | 1,866 / 7,498 | 33.0 / 910.7 | 93% | – | 12% | 0 |
| prefix-cache-off/full | 4 | 149 | 3.8 | 4,826 / 36,992 | 69.5 / 7403.0 | 92% | – | 65% | 0 |
| prefix-cache-off/full | 8 | 350 | 6.4 | 6,184 / 30,719 | 110.6 / 7939.1 | 93% | – | 62% | 0 |
| prefix-cache-off/truncate | 1 | 60 | 8.5 | 2,157 / 6,450 | 28.4 / 41.9 | 94% | – | 10% | 0 |
| prefix-cache-off/truncate | 2 | 98 | 10.1 | 2,509 / 7,165 | 34.2 / 1405.0 | 94% | – | 14% | 0 |
| prefix-cache-off/truncate | 4 | 180 | 6.2 | 3,635 / 14,416 | 56.0 / 2664.8 | 94% | – | 28% | 0 |
| prefix-cache-off/truncate | 8 | 385 | 10.2 | 4,439 / 14,140 | 83.9 / 5872.7 | 94% | – | 63% | 0 |
| prefix-cache-off/rolling | 1 | 48 | 17.9 | 767 / 1,780 | 26.8 / 32.8 | 71% | – | 4% | 0 |
| prefix-cache-off/rolling | 2 | 70 | 25.8 | 776 / 1,903 | 29.0 / 703.2 | 70% | – | 6% | 0 |
| prefix-cache-off/rolling | 4 | 180 | 18.0 | 1,280 / 4,180 | 36.5 / 2168.5 | 59% | – | 23% | 0 |
| prefix-cache-off/rolling | 8 | 383 | 24.8 | 1,744 / 4,822 | 60.9 / 2182.8 | 65% | – | 29% | 0 |
