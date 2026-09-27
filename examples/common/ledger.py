# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Decision ledger: the in-process view of an agent's institutional memory.

Every agent keeps a ledger. It is filled from two directions:

- records the agent writes itself (decisions it proposes, reviews it submits), and
- records other agents write, delivered by RetiQo as reflected attribute values.

The ledger has no RetiQo dependency, so the gate logic can be unit-tested offline.
"""
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

# Object classes and attributes shared by every example's State Channel Definition.
# tests/test_schemas.py checks that each schema.scd declares exactly these.
MEMORY_CLASSES: Dict[str, List[str]] = {
    "Decision": [
        "decisionId", "workflow", "subject", "proposal", "proposedBy",
        "rationale", "alternatives", "status", "version", "terms", "appliedLessons",
    ],
    "Review": ["reviewId", "decisionId", "version", "reviewer", "role", "verdict", "note"],
    "Objection": [
        "objectionId", "decisionId", "version", "raisedBy", "check", "reason",
        "blocking", "status", "resolution",
    ],
    "Outcome": ["outcomeId", "decisionId", "expected", "observed", "variance", "lesson"],
    # A lesson is reusable knowledge: which check to run, with what learned facts.
    "Lesson": ["lessonId", "workflow", "check", "facts", "summary", "learnedFrom", "learnedBy"],
}

# Notifications sent alongside the durable records.
MEMORY_INTERACTIONS: Dict[str, List[str]] = {
    "DecisionProposed": ["decisionId", "subject", "version"],
    "ReviewSubmitted": ["decisionId", "reviewer", "verdict"],
    "ObjectionRaised": ["decisionId", "objectionId", "blocking"],
    "DecisionFinalized": ["decisionId", "status"],
    "OutcomeRecorded": ["decisionId", "outcomeId"],
    "LessonRecorded": ["lessonId", "check"],
    # Free-text messages between agents about a decision, carried by RetiQo like any
    # other interaction, so the conversation is observable and attributable.
    "AgentMessage": ["fromAgent", "toAgent", "decisionId", "kind", "text"],
}

APPROVE, REJECT, CONCERN = "APPROVE", "REJECT", "CONCERN"
PROPOSED, APPROVED, BLOCKED, REJECTED = "PROPOSED", "APPROVED", "BLOCKED", "REJECTED"
OPEN, RESOLVED = "OPEN", "RESOLVED"


@dataclass
class Decision:
    decision_id: str
    workflow: str = ""
    subject: str = ""
    proposal: str = ""
    proposed_by: str = ""
    rationale: str = ""
    alternatives: str = ""
    status: str = PROPOSED
    version: int = 1
    terms: str = ""            # structured proposal (JSON) that reviewers check
    applied_lessons: str = ""  # comma-separated lesson IDs the proposer applied up front


@dataclass
class Review:
    review_id: str
    decision_id: str
    version: int
    reviewer: str
    role: str
    verdict: str
    note: str = ""


@dataclass
class Objection:
    objection_id: str
    decision_id: str
    version: int
    raised_by: str
    reason: str
    check: str = ""
    blocking: bool = True
    status: str = OPEN
    resolution: str = ""


@dataclass
class Outcome:
    outcome_id: str
    decision_id: str
    expected: str = ""
    observed: str = ""
    variance: str = ""
    lesson: str = ""


@dataclass
class Lesson:
    lesson_id: str
    workflow: str = ""
    check: str = ""
    facts: str = "{}"   # JSON
    summary: str = ""
    learned_from: str = ""
    learned_by: str = ""


@dataclass
class DecisionPolicy:
    """What a decision needs before it can be approved."""

    required_roles: Set[str] = field(default_factory=set)
    # A CONCERN is recorded but does not block; a REJECT always blocks.
    concerns_block: bool = False


@dataclass
class GateResult:
    approved: bool
    missing_roles: List[str]
    rejections: List[Review]
    open_blocking_objections: List[Objection]

    def explain(self) -> str:
        if self.approved:
            return "all required reviews approve and no blocking objection is open"
        reasons = []
        if self.missing_roles:
            reasons.append("waiting on " + ", ".join(self.missing_roles))
        for review in self.rejections:
            reasons.append(f"{review.role} rejected: {review.note}")
        for objection in self.open_blocking_objections:
            reasons.append(f"open objection from {objection.raised_by}: {objection.reason}")
        return "; ".join(reasons)


class DecisionLedger:
    """All decisions, reviews, objections and outcomes an agent knows about."""

    def __init__(self) -> None:
        self.decisions: Dict[str, Decision] = {}
        self.reviews: Dict[str, Review] = {}
        self.objections: Dict[str, Objection] = {}
        self.outcomes: Dict[str, Outcome] = {}
        self.lessons_by_id: Dict[str, Lesson] = {}

    # ----- ingest (from own writes or reflected attributes) -----------------

    def ingest(self, kind: str, values: Dict[str, str]) -> None:
        """Merge a record, given as attribute name -> string value, into the ledger."""
        if kind == "Decision" and values.get("decisionId"):
            record = self.decisions.setdefault(values["decisionId"], Decision(values["decisionId"]))
            _assign(record, values, {
                "workflow": "workflow", "subject": "subject", "proposal": "proposal",
                "proposedBy": "proposed_by", "rationale": "rationale",
                "alternatives": "alternatives", "status": "status", "terms": "terms",
                "appliedLessons": "applied_lessons",
            })
            if values.get("version"):
                record.version = int(values["version"])
        elif kind == "Review" and values.get("reviewId"):
            self.reviews[values["reviewId"]] = Review(
                review_id=values["reviewId"],
                decision_id=values.get("decisionId", ""),
                version=int(values.get("version") or 1),
                reviewer=values.get("reviewer", ""),
                role=values.get("role", ""),
                verdict=values.get("verdict", ""),
                note=values.get("note", ""),
            )
        elif kind == "Objection" and values.get("objectionId"):
            record = self.objections.setdefault(
                values["objectionId"],
                Objection(values["objectionId"], values.get("decisionId", ""), 1, "", ""),
            )
            _assign(record, values, {
                "decisionId": "decision_id", "raisedBy": "raised_by", "reason": "reason",
                "status": "status", "resolution": "resolution", "check": "check",
            })
            if values.get("version"):
                record.version = int(values["version"])
            if "blocking" in values:
                record.blocking = values["blocking"].lower() == "true"
        elif kind == "Outcome" and values.get("outcomeId"):
            record = self.outcomes.setdefault(
                values["outcomeId"], Outcome(values["outcomeId"], values.get("decisionId", ""))
            )
            _assign(record, values, {
                "decisionId": "decision_id", "expected": "expected", "observed": "observed",
                "variance": "variance", "lesson": "lesson",
            })
        elif kind == "Lesson" and values.get("lessonId"):
            record = self.lessons_by_id.setdefault(values["lessonId"], Lesson(values["lessonId"]))
            _assign(record, values, {
                "workflow": "workflow", "check": "check", "facts": "facts", "summary": "summary",
                "learnedFrom": "learned_from", "learnedBy": "learned_by",
            })

    # ----- queries ----------------------------------------------------------

    def reviews_for(self, decision_id: str, version: Optional[int] = None) -> List[Review]:
        return [
            r for r in self.reviews.values()
            if r.decision_id == decision_id and (version is None or r.version == version)
        ]

    def objections_for(self, decision_id: str) -> List[Objection]:
        return [o for o in self.objections.values() if o.decision_id == decision_id]

    def outcomes_for(self, decision_id: str) -> List[Outcome]:
        return [o for o in self.outcomes.values() if o.decision_id == decision_id]

    def evaluate(self, decision_id: str, policy: DecisionPolicy) -> GateResult:
        """Check the current version of a decision against a policy."""
        decision = self.decisions[decision_id]
        current = self.reviews_for(decision_id, decision.version)
        blocking_verdicts = {REJECT, CONCERN} if policy.concerns_block else {REJECT}

        # Latest review per role on the current version wins.
        latest_by_role: Dict[str, Review] = {}
        for review in current:
            latest_by_role[review.role] = review

        # A required role counts once it has reviewed the current version. A non-blocking
        # CONCERN still counts as a sign-off; it stays on record for later readers.
        missing = sorted(role for role in policy.required_roles if role not in latest_by_role)
        rejections = [r for r in latest_by_role.values() if r.verdict in blocking_verdicts]
        open_blocking = [
            o for o in self.objections_for(decision_id) if o.blocking and o.status == OPEN
        ]
        approved = not missing and not rejections and not open_blocking
        return GateResult(approved, missing, rejections, open_blocking)

    def history(self, workflow: Optional[str] = None, subject_contains: Optional[str] = None) -> List[Decision]:
        """Past decisions, optionally filtered by workflow or subject text."""
        found = []
        for decision in self.decisions.values():
            if workflow and decision.workflow != workflow:
                continue
            if subject_contains and subject_contains.lower() not in decision.subject.lower():
                continue
            found.append(decision)
        return found

    def lessons(self, workflow: Optional[str] = None) -> List[str]:
        """Lessons recorded against outcomes of past decisions."""
        result = []
        for decision in self.history(workflow):
            for outcome in self.outcomes_for(decision.decision_id):
                if outcome.lesson:
                    result.append(outcome.lesson)
        return result

    def lessons_for(self, workflow: str) -> List[Lesson]:
        """Structured lessons for a workflow, in the order they were learned."""
        return [lesson for lesson in self.lessons_by_id.values() if lesson.workflow == workflow]

    def render(self, decision_id: str) -> str:
        """Human-readable trail for one decision."""
        d = self.decisions[decision_id]
        lines = [
            f"Decision {d.decision_id} [{d.status}] v{d.version}: {d.subject}",
            f"  proposal:     {d.proposal}",
            f"  proposed by:  {d.proposed_by}",
            f"  rationale:    {d.rationale}",
        ]
        if d.alternatives:
            lines.append(f"  alternatives: {d.alternatives}")
        for r in sorted(self.reviews_for(decision_id), key=lambda r: (r.version, r.review_id)):
            lines.append(f"  review v{r.version} {r.role} ({r.reviewer}): {r.verdict} - {r.note}")
        for o in self.objections_for(decision_id):
            kind = "blocking" if o.blocking else "non-blocking"
            line = f"  objection ({kind}) from {o.raised_by}: {o.reason} [{o.status}]"
            if o.resolution:
                line += f" -> {o.resolution}"
            lines.append(line)
        for o in self.outcomes_for(decision_id):
            lines.append(f"  outcome: expected {o.expected}; observed {o.observed} ({o.variance})")
            if o.lesson:
                lines.append(f"  lesson:  {o.lesson}")
        return "\n".join(lines)


def _assign(record: object, values: Dict[str, str], mapping: Dict[str, str]) -> None:
    for attribute, field_name in mapping.items():
        if attribute in values:
            setattr(record, field_name, values[attribute])


def memory_attribute_names() -> Iterable[str]:
    for attributes in MEMORY_CLASSES.values():
        yield from attributes
