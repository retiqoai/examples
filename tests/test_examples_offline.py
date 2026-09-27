# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""Run every example end to end against the in-process simulation and check that knowledge
compounds: with institutional memory, recurring problems stop costing review cycles."""
import asyncio
import contextlib
import importlib.util
import io
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
LOOP_EXAMPLES = [
    "enterprise-multi-agent",
    "supply-chain-coordination",
    "ai-agent-marketplace",
    "federated-learning",
    "treasury-approvals",
    "options-hedging",
]


def _load(example: str):
    spec = importlib.util.spec_from_file_location(f"example_{example.replace('-', '_')}",
                                                  EXAMPLES / example / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(example: str) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(_load(example).run(offline=True))


@pytest.mark.parametrize("example", LOOP_EXAMPLES)
def test_memory_reduces_objections_and_review_time(example):
    result = _run(example)
    with_memory, without = result["with_memory"], result["without_memory"]
    assert with_memory["objections"] < without["objections"]
    assert with_memory["days"] < without["days"]
    assert with_memory["first_pass"] > without["first_pass"]


@pytest.mark.parametrize("example", LOOP_EXAMPLES)
def test_knowledge_accumulates_and_survives_the_agent_swap(example):
    rounds = _run(example)["per_round"]
    known = [r.lessons_known for r in rounds]
    assert known == sorted(known), "lessons on record never shrink"
    assert known[-1] > known[0]
    swapped = [i for i, r in enumerate(rounds) if r.proposer.endswith("-v2")]
    assert swapped, "the proposing agent is replaced partway through"
    first_new = swapped[0]
    assert rounds[first_new].lessons_known == rounds[first_new - 1].lessons_known + len(rounds[first_new - 1].learned)
    # The last decision goes through first time: everything it needs was learned earlier.
    assert rounds[-1].first_pass
    # Every lesson was learned exactly once; recurring problems were prevented, not re-learned.
    learned = [summary for r in rounds for summary in r.learned]
    assert len(learned) == len(set(learned))


def test_performance_test_offline():
    with contextlib.redirect_stdout(io.StringIO()):
        result = asyncio.run(_load("performance-test").run(offline=True, records=50, concurrency=10))
    assert result["arrived"] == 50
    assert result["lost_percent"] == 0


def test_options_hedging_transcript_shows_the_conversation():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        asyncio.run(_load("options-hedging").run(offline=True))
    transcript = out.getvalue()
    # Messages travel through RetiQo and are printed by the listening agent.
    assert "trading-agent -> desk  [PROPOSAL]" in transcript
    assert "[OBJECTION]" in transcript and "[LEARNED]" in transcript
    # The replacement agent announces what it inherited and cites where each lesson came from.
    assert "trading-agent-v2 -> desk  [HELLO]" in transcript
    assert "(learned in HEDGE-W01, by trading-agent)" in transcript
