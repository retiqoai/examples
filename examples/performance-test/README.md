<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Performance test: how fast decision records reach other agents

A writer agent proposes a batch of decisions; a reader agent in the same execution waits for each one to arrive in its ledger. The test reports write throughput, write-to-arrival latency (median, p95, p99) and the share of records that never arrived.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/performance-test
python main.py --offline                          # measures the simulation's own overhead only
python main.py                                    # against the RetiQo host configured in .env
PERF_RECORDS=2000 PERF_CONCURRENCY=100 python main.py
```

| Variable | Default | Meaning |
|---|---|---|
| `PERF_RECORDS` | 500 | Decisions to write |
| `PERF_CONCURRENCY` | 50 | Writes in flight at once |
| `PERF_TIMEOUT_SECONDS` | 60 | How long to wait for records to arrive |

Offline figures only describe the in-process simulation. Use a RetiQo host for numbers that mean anything.

Running against a host requires two agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the benchmark
- `schema.scd`: the shared memory classes only
