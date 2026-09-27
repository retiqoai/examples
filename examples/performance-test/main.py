# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Performance test: how fast decision records reach other agents.

A writer agent proposes a batch of decisions; a reader agent in the same execution waits
until each one appears in its ledger. The test reports write throughput and the latency
from write to arrival (median, p95, p99), and how many records never arrived.

    python main.py --offline                    # measures the in-process simulation only
    python main.py                              # against the RetiQo host configured in .env
    PERF_RECORDS=2000 PERF_CONCURRENCY=100 python main.py

Offline numbers only show the example's own overhead. Run against a host for real figures.
"""
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR.parent))

from common import ExecutionSession, banner, parse_args  # noqa: E402

RECORDS = int(os.getenv("PERF_RECORDS", "500"))
CONCURRENCY = int(os.getenv("PERF_CONCURRENCY", "50"))
ARRIVAL_TIMEOUT = float(os.getenv("PERF_TIMEOUT_SECONDS", "60"))


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


async def run(offline: bool, records: int = RECORDS, concurrency: int = CONCURRENCY) -> dict:
    session = ExecutionSession(EXAMPLE_DIR, "performance-test", offline)
    try:
        banner(f"Writing {records} decision records, {concurrency} at a time")
        writer = await session.join("writer-agent", "WriterAgent")
        reader = await session.join("reader-agent", "ReaderAgent")

        sent_at, arrived_at = {}, {}
        ingest = reader.memory.ledger.ingest

        def timed_ingest(kind, values):
            decision_id = values.get("decisionId")
            if kind == "Decision" and decision_id and decision_id not in arrived_at:
                arrived_at[decision_id] = time.perf_counter()
            ingest(kind, values)

        reader.memory.ledger.ingest = timed_ingest
        writer.memory.log = lambda message: None  # keep the output readable

        limit = asyncio.Semaphore(concurrency)

        async def write(i):
            decision_id = f"PERF-{i:06d}"
            async with limit:
                sent_at[decision_id] = time.perf_counter()
                await writer.memory.propose(decision_id, "performance-test", f"Record {i}",
                                            proposal="n/a", rationale="load test")

        start = time.perf_counter()
        await asyncio.gather(*(write(i) for i in range(records)))
        write_seconds = time.perf_counter() - start

        deadline = time.perf_counter() + ARRIVAL_TIMEOUT
        while len(arrived_at) < records and time.perf_counter() < deadline:
            await asyncio.sleep(0.05)

        latencies = [(arrived_at[k] - sent_at[k]) * 1000 for k in arrived_at if k in sent_at]
        results = {
            "records": records,
            "arrived": len(latencies),
            "lost_percent": round(100 * (records - len(latencies)) / records, 2),
            "writes_per_second": round(records / write_seconds, 1) if write_seconds else None,
            "median_ms": round(statistics.median(latencies), 2) if latencies else None,
            "p95_ms": round(percentile(latencies, 0.95), 2) if latencies else None,
            "p99_ms": round(percentile(latencies, 0.99), 2) if latencies else None,
        }

        banner("Results")
        for key, value in results.items():
            print(f"{key:>18}: {value}")
        if offline:
            print("\n(offline: this measures the in-process simulation, not a RetiQo host)")
        return results
    finally:
        await session.close()


if __name__ == "__main__":
    args = parse_args(__doc__.strip().splitlines()[0])
    asyncio.run(run(args.offline))
