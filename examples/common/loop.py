# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
The learning loop: many decisions over time, each one starting from what earlier ones taught.

A scenario is a sequence of real cases (quarterly reorders, payment runs, model rounds...)
handled by one proposing agent and several reviewing agents. Reviewers enforce the
organization's rules. When a reviewer objects, the proposer fixes the proposal and records
a Lesson in RetiQo: which check to run next time, and the facts it needs (a supplier's
minimum order, a verified bank account, a carrier's qualification...).

On every later case, the proposer reads all lessons from the shared record and applies the
ones that cover the case *before* proposing. Knowledge compounds: objections that happened
once stop recurring, and only genuinely new problems cost a review cycle.

Midway, the proposing agent is replaced. The replacement has no context of its own; it
catches up from the shared record, so the improvement does not reset.

Running the same cases with use_memory=False (the proposer ignores the record) is the
control: the same objections recur on every case.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .ledger import APPROVE, REJECT, DecisionPolicy
from .records import DomainRecords
from .runtime import Agent, ExecutionSession

Case = Dict[str, object]
Terms = Dict[str, object]
Facts = Dict[str, object]


@dataclass
class Rule:
    """One organizational rule, enforced by the reviewer with `role`."""

    check: str
    role: str
    # (case, terms) -> reason the proposal breaks the rule, or None
    violated: Callable[[Case, Terms], Optional[str]]
    # (case, terms) -> facts worth remembering once the rule has been broken
    learn: Callable[[Case, Terms], Facts]
    # (case, facts) -> does a remembered lesson apply to this new case?
    covers: Callable[[Case, Facts], bool]
    # (case, terms, facts) -> terms that satisfy the rule
    fix: Callable[[Case, Terms, Facts], Terms]
    # facts -> the lesson in one sentence
    summary: Callable[[Facts], str]


@dataclass
class Participant:
    name: str
    actor_type: str
    role: str = ""


@dataclass
class Scenario:
    title: str
    workflow: str
    decision_prefix: str
    proposer: Participant
    reviewers: List[Participant]
    rules: List[Rule]
    cases: List[Case]
    base_terms: Callable[[Case], Terms]
    describe: Callable[[Terms], str]
    subject: Callable[[Case], str]
    # (case, terms) -> (expected, observed) for the Outcome record
    outcome: Callable[[Case, Terms], Tuple[str, str]]
    review_cycle_days: int = 2
    # Replace the proposing agent before this decision (1-based); 0 disables the swap.
    swap_before_round: int = 0
    # Optional domain record written for every approved decision:
    # (class name, attributes, (case, terms, decision_id) -> (object name, values))
    domain_record: Optional[Tuple[str, List[str], Callable[[Case, Terms, str], Tuple[str, Dict[str, str]]]]] = None
    delay_cost_label: str = "delay cost"

    def rule(self, check: str) -> Rule:
        return next(r for r in self.rules if r.check == check)


@dataclass
class RoundMetrics:
    round: int
    period: str
    proposer: str
    lessons_known: int
    lessons_applied: int
    objections: int
    revisions: int
    first_pass: bool
    days: int
    delay_cost: float
    learned: List[str] = field(default_factory=list)


async def run_loop(scenario: Scenario, example_dir: Path, offline: bool, use_memory: bool = True,
                   verbose: bool = True, conversation: bool = False) -> List[RoundMetrics]:
    """Run every case. With conversation=True the agents also talk to each other through
    RetiQo, and a listening agent prints the exchange as a transcript."""
    say = print if verbose and not conversation else (lambda *_: None)
    header = print if verbose else (lambda *_: None)
    session = ExecutionSession(example_dir, scenario.decision_prefix.lower(), offline)
    policy = DecisionPolicy(required_roles={r.role for r in scenario.reviewers})
    metrics: List[RoundMetrics] = []
    try:
        proposer = await session.join(scenario.proposer.name, scenario.proposer.actor_type)
        reviewers = [(await session.join(p.name, p.actor_type), p.role) for p in scenario.reviewers]
        for agent in [proposer] + [a for a, _ in reviewers]:
            agent.memory.log = lambda *_: None  # the loop prints its own, shorter narration
        chat = Chat(enabled=conversation)
        if conversation:
            # A listener that only reads: it prints every message exactly as RetiQo delivered it.
            listener = await session.join("desk-log", "TranscriptListener")
            listener.memory.log = lambda *_: None
            listener.actor.on_message = print_message

        domain = None
        if scenario.domain_record:
            domain = DomainRecords(proposer.rti)
            await domain.declare(scenario.domain_record[0], scenario.domain_record[1])

        for number, case in enumerate(scenario.cases, start=1):
            if scenario.swap_before_round and number == scenario.swap_before_round:
                proposer, domain = await _replace_proposer(session, scenario, proposer, say, header, chat)

            header(f"\n{'=' * 8} Decision {number} | {case['period']} | {scenario.subject(case)} {'=' * 8}"
                   if conversation else f"\nDecision {number} | {case['period']} | {scenario.subject(case)}")
            row = await _run_case(scenario, policy, number, case, proposer, reviewers,
                                  domain, use_memory, say, chat)
            metrics.append(row)
        return metrics
    finally:
        await session.close()


async def _replace_proposer(session: ExecutionSession, scenario: Scenario, old: Agent, say, header, chat):
    name = f"{scenario.proposer.name}-v2"
    header(f"\n--- {old.name} is replaced by {name} (new model, no local context) ---")
    new = await session.join(name, scenario.proposer.actor_type)
    new.memory.log = lambda *_: None
    known = len(old.memory.ledger.lessons_by_id)
    await new.memory.wait_for(lambda ledger: len(ledger.lessons_by_id) >= known)
    say(f"    {name} recovered {known} lesson(s) and "
        f"{len(new.memory.ledger.decisions)} past decision(s) from the shared record")
    await chat.send(old, "desk", "HANDOVER", f"Handing over to {name}. Everything I learned is in the shared record.")
    await chat.send(new, "desk", "HELLO",
                    f"Taking over from {old.name}. I have no memory of my own; from the shared record I "
                    f"loaded {known} lesson(s) and {len(new.memory.ledger.decisions)} past decision(s).")
    await session.leave(old)
    domain = None
    if scenario.domain_record:
        domain = DomainRecords(new.rti)
        await domain.declare(scenario.domain_record[0], scenario.domain_record[1])
    return new, domain


async def _run_case(scenario, policy, number, case, proposer: Agent, reviewers, domain,
                    use_memory, say, chat) -> RoundMetrics:
    ledger = proposer.memory.ledger
    decision_id = f"{scenario.decision_prefix}-{case['id']}"

    # 1. Start from the base proposal, then apply every remembered lesson that covers this case.
    lessons = ledger.lessons_for(scenario.workflow) if use_memory else []
    terms, applied = _apply_lessons(scenario, case, scenario.base_terms(case), lessons)
    if applied:
        say(f"    {len(lessons)} lesson(s) on record; {len(applied)} changed this plan:")
        for lesson in applied:
            say(f"      - {lesson.summary}")

    if use_memory:
        if not lessons:
            recall = "Checked the shared record: no lessons on file yet. Starting from the standard plan."
        elif not applied:
            recall = f"Checked the shared record: {len(lessons)} lesson(s) on file; none change this plan."
        else:
            recall = (f"Checked the shared record: {len(lessons)} lesson(s) on file; {len(applied)} apply here:\n"
                      + "\n".join(f"- {l.summary} (learned in {l.learned_from}, by {l.learned_by})"
                                   for l in applied))
        skipped = [l for l in lessons if l not in applied]
        if applied and skipped:
            recall += "\nOn file but not relevant to this case:\n" + "\n".join(f"- {l.summary}" for l in skipped)
        await chat.send(proposer, "desk", "RECALL", recall, decision_id)

    await proposer.memory.propose(
        decision_id, scenario.workflow, subject=scenario.subject(case),
        proposal=scenario.describe(terms),
        rationale="Base plan" + (f" with {len(applied)} lesson(s) applied" if applied else ""),
        terms=json.dumps(terms, sort_keys=True),
        applied_lessons=",".join(l.lesson_id for l in applied),
    )
    say(f"    proposed: {scenario.describe(terms)}")
    await chat.send(proposer, "desk", "PROPOSAL", f"Proposal v1: {scenario.describe(terms)}", decision_id)

    objections = revisions = 0
    learned: List[str] = []
    while True:
        version = ledger.decisions[decision_id].version
        for agent, role in reviewers:
            await _review(scenario, case, agent, role, decision_id, version, say, chat, proposer.name)
        await proposer.memory.wait_for(
            lambda l: len({r.role for r in l.reviews_for(decision_id, version)}) == len(reviewers))
        result = await proposer.memory.finalize(decision_id, policy)
        if result.approved:
            break

        # 2. Blocked: fix what the reviewers objected to, and remember it.
        await proposer.memory.wait_for(
            lambda l: all(o.check for o in l.objections_for(decision_id) if o.status == "OPEN"))
        open_objections = [o for o in ledger.objections_for(decision_id) if o.status == "OPEN"]
        order = {rule.check: i for i, rule in enumerate(scenario.rules)}
        for objection in sorted(open_objections, key=lambda o: order[o.check]):
            objections += 1
            rule = scenario.rule(objection.check)
            facts = rule.learn(case, terms)
            terms = rule.fix(case, terms, facts)
            summary = rule.summary(facts)
            known_before = len(ledger.lessons_by_id)
            await proposer.memory.record_lesson(scenario.workflow, rule.check, facts, summary, decision_id)
            if len(ledger.lessons_by_id) > known_before:
                learned.append(summary)
                say(f"    learned: {summary}")
                await chat.send(proposer, objection.raised_by, "LEARNED",
                                f"Understood. Fixing it and recording the lesson for next time: {summary}",
                                decision_id)
            else:
                say(f"    (already on record: {summary})")
                await chat.send(proposer, objection.raised_by, "ACK",
                                f"Understood; this is already on record: {summary}", decision_id)
        if use_memory:
            # A fix can change the plan (a different supplier, carrier or provider), so run
            # every known lesson again against the revised plan.
            terms, _ = _apply_lessons(scenario, case, terms, ledger.lessons_for(scenario.workflow))
        revisions += 1
        if revisions > 5:
            raise RuntimeError(f"{decision_id}: still blocked after 5 revisions; check the scenario's fixes")
        await proposer.memory.revise(decision_id, scenario.describe(terms),
                                     "Revised to address: " + ", ".join(o.check for o in open_objections),
                                     terms=json.dumps(terms, sort_keys=True))
        say(f"    revised v{version + 1}: {scenario.describe(terms)}")
        await chat.send(proposer, "desk", "PROPOSAL", f"Proposal v{version + 1}: {scenario.describe(terms)}",
                        decision_id)

    days = scenario.review_cycle_days * (1 + revisions)
    delay_cost = float(case.get("cost_per_day", 0)) * scenario.review_cycle_days * revisions
    verdict = "first time" if revisions == 0 else f"after {revisions} revision(s)"
    say(f"    APPROVED {verdict}, {days} days" + (f", {scenario.delay_cost_label} ${delay_cost:,.0f}" if delay_cost else ""))

    record_note = ""
    if domain is not None:
        name, values = scenario.domain_record[2](case, terms, decision_id)
        await domain.write(scenario.domain_record[0], name, values)
        record_note = f" {scenario.domain_record[0]} {name} written, linked to {decision_id}."
    await chat.send(proposer, "desk", "DONE",
                    f"All reviewers approved v{revisions + 1} "
                    + ("first time." if revisions == 0 else f"after {revisions} revision(s).") + record_note,
                    decision_id)

    expected, observed = scenario.outcome(case, terms)
    await proposer.memory.record_outcome(
        decision_id, expected=expected, observed=observed,
        variance=f"{revisions} revision(s), {days} days to approval",
        lesson="; ".join(learned),
    )
    return RoundMetrics(
        round=number, period=str(case["period"]), proposer=proposer.name,
        lessons_known=len(lessons) if use_memory else 0, lessons_applied=len(applied),
        objections=objections, revisions=revisions, first_pass=revisions == 0,
        days=days, delay_cost=delay_cost, learned=learned,
    )


class Chat:
    """Messages between agents, sent through RetiQo as AgentMessage interactions."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    async def send(self, agent: Agent, to: str, kind: str, text: str, decision_id: str = "") -> None:
        if self.enabled:
            await agent.memory.message(to, kind, text, decision_id)


def print_message(message: Dict[str, str]) -> None:
    """Print one AgentMessage as a transcript line."""
    lines = message.get("text", "").split("\n")
    print(f"{message.get('fromAgent', '?')} -> {message.get('toAgent', '?')}  [{message.get('kind', '')}]")
    for line in lines:
        print(f"    {line}")


def _apply_lessons(scenario, case, terms, lessons):
    """Apply every lesson that covers this case, in the scenario's rule order (not the order
    lessons were learned), so fixes compose the same way every time."""
    applied = []
    for rule in scenario.rules:
        for lesson in (l for l in lessons if l.check == rule.check):
            facts = json.loads(lesson.facts)
            if rule.covers(case, facts):
                fixed = rule.fix(case, terms, facts)
                if fixed != terms:  # count a lesson only when it changed the plan
                    applied.append(lesson)
                terms = fixed
    return terms, applied


async def _review(scenario, case, agent: Agent, role: str, decision_id: str, version: int, say,
                  chat, proposer_name: str):
    """A reviewer checks the current version against the rules it owns."""
    await agent.memory.wait_for(
        lambda l: decision_id in l.decisions and l.decisions[decision_id].version == version)
    ledger = agent.memory.ledger
    terms = json.loads(ledger.decisions[decision_id].terms)
    violations = {}
    for rule in scenario.rules:
        if rule.role == role:
            reason = rule.violated(case, terms)
            if reason:
                violations[rule.check] = reason

    mine = [o for o in ledger.objections_for(decision_id) if o.raised_by == agent.name and o.status == "OPEN"]
    for objection in mine:
        if objection.check not in violations:
            await agent.memory.resolve_objection(objection.objection_id, f"fixed in v{version}")
            await chat.send(agent, proposer_name, "RESOLVED",
                            f"[{objection.check}] fixed in v{version}. Objection withdrawn.", decision_id)
    already_open = {o.check for o in mine}
    for check, reason in violations.items():
        if check not in already_open:
            await agent.memory.object(decision_id, reason, blocking=True, check=check)
            say(f"    {agent.name} objected [{check}]: {reason}")
            await chat.send(agent, proposer_name, "OBJECTION", f"[{check}] {reason}", decision_id)

    if violations:
        await agent.memory.review(decision_id, role, REJECT, "; ".join(violations))
    else:
        checks = [rule.check for rule in scenario.rules if rule.role == role]
        await agent.memory.review(decision_id, role, APPROVE, "meets " + role + " rules")
        await chat.send(agent, proposer_name, "APPROVED",
                        f"v{version} approved. Checked: {', '.join(checks)}.", decision_id)


def compare(scenario: Scenario, with_memory: List[RoundMetrics], without: List[RoundMetrics]) -> dict:
    """Print the round-by-round comparison and return the totals."""
    print()
    print("=" * 96)
    print(f"{scenario.title}: with institutional memory vs without")
    print("=" * 96)
    header = (f"{'#':>5}  {'period':<10} {'lessons known':>13} {'applied':>7} "
              f"{'objections':>10} {'revisions':>9} {'days':>5}   | {'without memory: objections':>26} {'days':>5}")
    print(header)
    print("-" * len(header))
    for a, b in zip(with_memory, without):
        swap = "  <- new agent" if a.proposer.endswith("-v2") and (a.round == 1 or with_memory[a.round - 2].proposer != a.proposer) else ""
        print(f"{a.round:>5}  {a.period:<10} {a.lessons_known:>13} {a.lessons_applied:>7} "
              f"{a.objections:>10} {a.revisions:>9} {a.days:>5}   | {b.objections:>26} {b.days:>5}{swap}")

    def totals(rows):
        return {
            "objections": sum(r.objections for r in rows),
            "revisions": sum(r.revisions for r in rows),
            "days": sum(r.days for r in rows),
            "delay_cost": sum(r.delay_cost for r in rows),
            "first_pass": sum(1 for r in rows if r.first_pass),
            "lessons": sum(len(r.learned) for r in rows),
        }

    t_with, t_without = totals(with_memory), totals(without)
    print("-" * len(header))
    print(f"{'total':>5}  {'':<10} {t_with['lessons']:>13} {'':>7} {t_with['objections']:>10} "
          f"{t_with['revisions']:>9} {t_with['days']:>5}   | {t_without['objections']:>26} {t_without['days']:>5}")
    n = len(with_memory)
    print()
    print(f"Approved first time: {t_with['first_pass']}/{n} with memory, {t_without['first_pass']}/{n} without")
    print(f"Days spent in review: {t_with['days']} with memory, {t_without['days']} without")
    if t_with["delay_cost"] or t_without["delay_cost"]:
        print(f"{scenario.delay_cost_label.capitalize()}: ${t_with['delay_cost']:,.0f} with memory, "
              f"${t_without['delay_cost']:,.0f} without")
    return {"with_memory": t_with, "without_memory": t_without, "rounds": n}
