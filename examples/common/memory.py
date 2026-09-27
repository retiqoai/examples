# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Institutional memory on RetiQo: decisions, reviews, objections and outcomes as shared state.

Each record is a RetiQo object instance, owned by the agent that wrote it:

- the proposer owns its Decision (and is the only one who changes its status),
- each reviewer owns its Review,
- whoever objects owns the Objection (and withdraws or resolves it),
- whoever observes the result owns the Outcome.

Other agents see these records through subscriptions, so every participant, including an
agent that joins later, works from the same record of what was decided and why.
"""
import asyncio
import hashlib
import json
from typing import Callable, Dict, Optional, Tuple

from retiqo.rti.attribute_handle_set import AttributeHandleSetFactory
from retiqo.rti.supplied_attributes import SuppliedAttributesFactory
from retiqo.rti.supplied_parameters import SuppliedParametersFactory

from .ledger import (
    APPROVED, BLOCKED, MEMORY_CLASSES, MEMORY_INTERACTIONS, OPEN, PROPOSED, RESOLVED,
    Decision, DecisionLedger, DecisionPolicy, GateResult, Lesson, Objection, Outcome, Review,
)


class InstitutionalMemory:
    """Read and write decision records in a RetiQo state channel execution."""

    def __init__(self, rti, agent_name: str, ledger: Optional[DecisionLedger] = None,
                 log: Callable[[str], None] = print) -> None:
        self.rti = rti
        self.agent_name = agent_name
        self.ledger = ledger or DecisionLedger()
        self.log = log
        self.class_handles: Dict[str, int] = {}
        self.attribute_handles: Dict[str, Dict[str, int]] = {}
        self.interaction_handles: Dict[str, int] = {}
        self.parameter_handles: Dict[str, Dict[str, int]] = {}
        # object handle -> memory class name, for everything we can see
        self._object_kinds: Dict[int, str] = {}
        # object name -> (kind, handle, values) for records this agent owns
        self._owned: Dict[str, Tuple[str, int, Dict[str, str]]] = {}
        self._class_by_handle: Dict[int, str] = {}
        self._objection_count = 0

    # ----- setup ------------------------------------------------------------

    async def connect(self, request_existing: bool = True) -> None:
        """Resolve handles, publish and subscribe to every memory class."""
        for kind, attributes in MEMORY_CLASSES.items():
            handle = await self.rti.get_object_class_handle(f"ObjectRoot.{kind}")
            self.class_handles[kind] = handle
            self._class_by_handle[handle] = kind
            self.attribute_handles[kind] = {
                name: await self.rti.get_attribute_handle(name, handle) for name in attributes
            }
            handle_set = AttributeHandleSetFactory.create(list(self.attribute_handles[kind].values()))
            await self.rti.publish_object_class(handle, handle_set)
            await self.rti.subscribe_object_class_attributes(handle, handle_set)

        for name, parameters in MEMORY_INTERACTIONS.items():
            handle = await self.rti.get_interaction_class_handle(f"InteractionRoot.{name}")
            self.interaction_handles[name] = handle
            self.parameter_handles[name] = {
                p: await self.rti.get_parameter_handle(p, handle) for p in parameters
            }
            await self.rti.publish_interaction_class(handle)
            await self.rti.subscribe_interaction_class(handle)

        if request_existing:
            # Ask current owners to send their latest values, so an agent that joins
            # late starts from the full record instead of an empty one.
            for kind, handle in self.class_handles.items():
                attrs = AttributeHandleSetFactory.create(list(self.attribute_handles[kind].values()))
                try:
                    await self.rti.request_class_attribute_value_update(handle, attrs)
                except Exception as exc:  # the call is advisory; carry on without it
                    self.log(f"[{self.agent_name}] could not request existing {kind} records: {exc}")

    # ----- writing records --------------------------------------------------

    async def propose(self, decision_id: str, workflow: str, subject: str, proposal: str,
                      rationale: str, alternatives: str = "", terms: str = "",
                      applied_lessons: str = "") -> Decision:
        values = {
            "decisionId": decision_id, "workflow": workflow, "subject": subject,
            "proposal": proposal, "proposedBy": self.agent_name, "rationale": rationale,
            "alternatives": alternatives, "status": PROPOSED, "version": "1",
            "terms": terms, "appliedLessons": applied_lessons,
        }
        await self._write("Decision", decision_id, values)
        await self._notify("DecisionProposed", decisionId=decision_id, subject=subject, version="1")
        self.log(f"[{self.agent_name}] proposed {decision_id}: {proposal}")
        return self.ledger.decisions[decision_id]

    async def revise(self, decision_id: str, proposal: str, rationale: str,
                     terms: Optional[str] = None) -> Decision:
        """Publish a new version of a decision this agent proposed. Earlier reviews stay on
        record but no longer count, because they were given on the old version."""
        decision = self.ledger.decisions[decision_id]
        version = decision.version + 1
        changes = {"proposal": proposal, "rationale": rationale, "status": PROPOSED,
                   "version": str(version)}
        if terms is not None:
            changes["terms"] = terms
        await self._update("Decision", decision_id, changes)
        await self._notify("DecisionProposed", decisionId=decision_id, subject=decision.subject,
                           version=str(version))
        self.log(f"[{self.agent_name}] revised {decision_id} to v{version}: {proposal}")
        return self.ledger.decisions[decision_id]

    async def review(self, decision_id: str, role: str, verdict: str, note: str) -> Review:
        version = self.ledger.decisions[decision_id].version
        review_id = f"{decision_id}/v{version}/{role}"
        await self._write("Review", review_id, {
            "reviewId": review_id, "decisionId": decision_id, "version": str(version),
            "reviewer": self.agent_name, "role": role, "verdict": verdict, "note": note,
        })
        await self._notify("ReviewSubmitted", decisionId=decision_id, reviewer=self.agent_name,
                           verdict=verdict)
        self.log(f"[{self.agent_name}] reviewed {decision_id} v{version} as {role}: {verdict} ({note})")
        return self.ledger.reviews[review_id]

    async def object(self, decision_id: str, reason: str, blocking: bool = True,
                     check: str = "") -> Objection:
        self._objection_count += 1
        objection_id = f"{decision_id}/objection-{self.agent_name}-{self._objection_count}"
        version = self.ledger.decisions[decision_id].version
        await self._write("Objection", objection_id, {
            "objectionId": objection_id, "decisionId": decision_id, "version": str(version),
            "raisedBy": self.agent_name, "check": check, "reason": reason,
            "blocking": "true" if blocking else "false", "status": OPEN, "resolution": "",
        })
        await self._notify("ObjectionRaised", decisionId=decision_id, objectionId=objection_id,
                           blocking="true" if blocking else "false")
        kind = "blocking" if blocking else "non-blocking"
        self.log(f"[{self.agent_name}] raised a {kind} objection on {decision_id}: {reason}")
        return self.ledger.objections[objection_id]

    async def resolve_objection(self, objection_id: str, resolution: str) -> Objection:
        await self._update("Objection", objection_id, {"status": RESOLVED, "resolution": resolution})
        self.log(f"[{self.agent_name}] resolved {objection_id}: {resolution}")
        return self.ledger.objections[objection_id]

    async def finalize(self, decision_id: str, policy: DecisionPolicy) -> GateResult:
        """Apply the policy to the current record and set the decision's status."""
        result = self.ledger.evaluate(decision_id, policy)
        status = APPROVED if result.approved else BLOCKED
        await self._update("Decision", decision_id, {"status": status})
        await self._notify("DecisionFinalized", decisionId=decision_id, status=status)
        self.log(f"[{self.agent_name}] {decision_id} is {status}: {result.explain()}")
        return result

    async def record_outcome(self, decision_id: str, expected: str, observed: str,
                             variance: str, lesson: str) -> Outcome:
        outcome_id = f"{decision_id}/outcome"
        await self._write("Outcome", outcome_id, {
            "outcomeId": outcome_id, "decisionId": decision_id, "expected": expected,
            "observed": observed, "variance": variance, "lesson": lesson,
        })
        await self._notify("OutcomeRecorded", decisionId=decision_id, outcomeId=outcome_id)
        self.log(f"[{self.agent_name}] recorded outcome for {decision_id}: {observed}")
        return self.ledger.outcomes[outcome_id]

    async def record_lesson(self, workflow: str, check: str, facts: Dict[str, object],
                            summary: str, learned_from: str) -> Lesson:
        """Keep a reusable lesson: the check to run next time, and the facts it needs.
        Recording the same check with the same facts twice is a no-op."""
        facts_json = json.dumps(facts, sort_keys=True)
        digest = hashlib.sha256(f"{check}|{facts_json}".encode()).hexdigest()[:10]
        lesson_id = f"{workflow}/{check}/{digest}"
        if lesson_id in self.ledger.lessons_by_id:
            return self.ledger.lessons_by_id[lesson_id]
        await self._write("Lesson", lesson_id, {
            "lessonId": lesson_id, "workflow": workflow, "check": check, "facts": facts_json,
            "summary": summary, "learnedFrom": learned_from, "learnedBy": self.agent_name,
        })
        await self._notify("LessonRecorded", lessonId=lesson_id, check=check)
        self.log(f"[{self.agent_name}] learned: {summary}")
        return self.ledger.lessons_by_id[lesson_id]

    async def message(self, to: str, kind: str, text: str, decision_id: str = "") -> None:
        """Send a message to another agent (or "desk" for everyone) through RetiQo."""
        await self._notify("AgentMessage", fromAgent=self.agent_name, toAgent=to,
                           decisionId=decision_id, kind=kind, text=text)

    def decode_message(self, interaction_class: int, the_interaction) -> Optional[Dict[str, str]]:
        """Return the fields of an AgentMessage, or None for any other interaction."""
        if interaction_class != self.interaction_handles.get("AgentMessage"):
            return None
        names = {handle: name for name, handle in self.parameter_handles["AgentMessage"].items()}
        return {
            names[handle]: value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
            for handle, value in the_interaction if handle in names
        }

    async def wait_for(self, predicate: Callable[[DecisionLedger], bool],
                       timeout: float = 10.0, interval: float = 0.05) -> None:
        """Wait until other agents' records have arrived and the predicate holds.
        Raises TimeoutError if they do not arrive in time."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                if predicate(self.ledger):
                    return
            except KeyError:
                pass  # the record the predicate reads has not arrived yet
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    f"[{self.agent_name}] expected records did not arrive within {timeout}s; "
                    "check that every agent joined the same execution and subscribed")
            await asyncio.sleep(interval)

    # ----- callbacks, forwarded by MemoryActor ------------------------------

    def on_discover(self, the_object: int, the_object_class: int) -> None:
        kind = self._class_by_handle.get(the_object_class)
        if kind:
            self._object_kinds[the_object] = kind

    def on_reflect(self, the_object: int, the_attributes) -> None:
        kind = self._object_kinds.get(the_object)
        if not kind:
            return
        names = {handle: name for name, handle in self.attribute_handles[kind].items()}
        values = {}
        for handle, raw in the_attributes:
            if handle in names:
                values[names[handle]] = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        self.ledger.ingest(kind, values)

    async def on_provide(self, the_object: int) -> None:
        """Another agent asked for current values; resend the record if we own it."""
        for kind, handle, values in self._owned.values():
            if handle == the_object:
                await self._send_values(kind, handle, values, tag=b"provide")

    # ----- internals --------------------------------------------------------

    async def _write(self, kind: str, key: str, values: Dict[str, str]) -> None:
        name = f"{kind}:{key}"
        handle = await self.rti.register_object_instance(self.class_handles[kind], name)
        self._owned[name] = (kind, handle, dict(values))
        self._object_kinds[handle] = kind
        self.ledger.ingest(kind, values)
        await self._send_values(kind, handle, values, tag=kind.lower().encode())

    async def _update(self, kind: str, key: str, changes: Dict[str, str]) -> None:
        name = f"{kind}:{key}"
        if name not in self._owned:
            raise PermissionError(f"{self.agent_name} does not own {name}; only its owner can change it")
        _, handle, values = self._owned[name]
        values.update(changes)
        self.ledger.ingest(kind, values)
        # Send the whole record, not just the changed fields, so every reflection is
        # self-describing and a late reader never sees a partial record.
        await self._send_values(kind, handle, values, tag=b"update")

    async def _send_values(self, kind: str, handle: int, values: Dict[str, str], tag: bytes) -> None:
        supplied = SuppliedAttributesFactory.create()
        for name, value in values.items():
            supplied.add(self.attribute_handles[kind][name], str(value).encode("utf-8"))
        await self.rti.update_attribute_values(handle, supplied, tag)

    async def _notify(self, interaction: str, **parameters: str) -> None:
        params = SuppliedParametersFactory.create()
        for name, value in parameters.items():
            params.add(self.parameter_handles[interaction][name], str(value).encode("utf-8"))
        await self.rti.send_interaction(self.interaction_handles[interaction], params,
                                        interaction.encode("utf-8"))
