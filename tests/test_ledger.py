# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""Decision gate logic, with no RetiQo connection."""
from common.ledger import APPROVE, CONCERN, REJECT, DecisionLedger, DecisionPolicy


def _ledger_with_decision(version: int = 1) -> DecisionLedger:
    ledger = DecisionLedger()
    ledger.ingest("Decision", {"decisionId": "D1", "workflow": "w", "subject": "s",
                               "status": "PROPOSED", "version": str(version)})
    return ledger


def _review(ledger, role, verdict, version=1):
    ledger.ingest("Review", {"reviewId": f"D1/v{version}/{role}", "decisionId": "D1",
                             "version": str(version), "reviewer": role, "role": role,
                             "verdict": verdict, "note": ""})


POLICY = DecisionPolicy(required_roles={"finance", "inventory"})


def test_missing_role_blocks():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", APPROVE)
    result = ledger.evaluate("D1", POLICY)
    assert not result.approved
    assert result.missing_roles == ["inventory"]


def test_all_roles_approve():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", APPROVE)
    _review(ledger, "inventory", APPROVE)
    assert ledger.evaluate("D1", POLICY).approved


def test_reject_blocks():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", APPROVE)
    _review(ledger, "inventory", REJECT)
    result = ledger.evaluate("D1", POLICY)
    assert not result.approved
    assert [r.role for r in result.rejections] == ["inventory"]


def test_concern_counts_as_signoff_unless_policy_says_otherwise():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", CONCERN)
    _review(ledger, "inventory", APPROVE)
    assert ledger.evaluate("D1", POLICY).approved
    strict = DecisionPolicy(required_roles={"finance", "inventory"}, concerns_block=True)
    assert not ledger.evaluate("D1", strict).approved


def test_open_blocking_objection_blocks_until_resolved():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", APPROVE)
    _review(ledger, "inventory", APPROVE)
    ledger.ingest("Objection", {"objectionId": "O1", "decisionId": "D1", "version": "1",
                                "raisedBy": "controls", "reason": "r", "blocking": "true",
                                "status": "OPEN"})
    assert not ledger.evaluate("D1", POLICY).approved
    ledger.ingest("Objection", {"objectionId": "O1", "status": "RESOLVED", "resolution": "ok"})
    assert ledger.evaluate("D1", POLICY).approved


def test_non_blocking_objection_does_not_block():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", APPROVE)
    _review(ledger, "inventory", APPROVE)
    ledger.ingest("Objection", {"objectionId": "O1", "decisionId": "D1", "raisedBy": "x",
                                "reason": "r", "blocking": "false", "status": "OPEN"})
    assert ledger.evaluate("D1", POLICY).approved


def test_reviews_on_old_version_do_not_count():
    ledger = _ledger_with_decision()
    _review(ledger, "finance", APPROVE, version=1)
    _review(ledger, "inventory", APPROVE, version=1)
    ledger.ingest("Decision", {"decisionId": "D1", "version": "2"})
    result = ledger.evaluate("D1", POLICY)
    assert not result.approved
    assert result.missing_roles == ["finance", "inventory"]


def test_history_and_lessons():
    ledger = _ledger_with_decision()
    ledger.ingest("Outcome", {"outcomeId": "D1/outcome", "decisionId": "D1",
                              "observed": "ok", "lesson": "check inbound orders"})
    assert [d.decision_id for d in ledger.history(workflow="w")] == ["D1"]
    assert ledger.lessons(workflow="w") == ["check inbound orders"]
    assert "check inbound orders" in ledger.render("D1")
