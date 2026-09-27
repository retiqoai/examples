# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Treasury approvals: ten payment runs, and the controls knowledge that builds up between them.

An accounts-payable agent proposes each supplier payment. Controls, Treasury and Vendor
Compliance agents enforce the rules that protect the company: verify changed bank details
by call-back, catch duplicate invoices, take early-payment discounts, collect a W-9 before
paying a new vendor, and require dual approval for large payments.

Each objection leaves a lesson in RetiQo: a verified account, a supplier's discount terms,
a duplicate pattern, a policy threshold. The next payment run starts from all of them.
Before run six the payables agent is replaced; the replacement reads the record and keeps
going. The ten runs are then replayed without institutional memory for comparison.

    python main.py --offline      # in-process simulation, no RetiQo host needed
    python main.py                # against the RetiQo host configured in .env
"""
import asyncio
import re
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR.parent))

from common import banner, parse_args  # noqa: E402
from common.loop import Participant, Rule, Scenario, compare, run_loop  # noqa: E402

DUAL_APPROVAL_THRESHOLD = 100_000

# Vendor master: payment terms as agreed in each contract. "2/10 net 30" means 2% off if
# paid within 10 days, otherwise due in 30.
TERMS = {
    "Pinecrest Toys": "net 30",
    "Harbor Freightways": "2/10 net 30",
    "Qualis Labs": "net 30",
    "Novik Supply": "net 30",
}

# Ten weekly payment runs. `paid_before` is what the AP system has already paid.
# All companies, invoices and account fragments are fictional.
CASES = [
    dict(id="RUN01", period="Week 1", vendor="Pinecrest Toys", invoice="INV-88213", amount=48_250.00,
         account="4471", verified_accounts=["0932"], new_vendor=False, paid_before=[],
         observed="Settled; bank change confirmed by Pinecrest's controller"),
    dict(id="RUN02", period="Week 2", vendor="Harbor Freightways", invoice="HF-5521", amount=12_400.00,
         account="1180", verified_accounts=["1180"], new_vendor=False, paid_before=[],
         observed="Paid on day 10; 2% discount captured"),
    dict(id="RUN03", period="Week 3", vendor="Pinecrest Toys", invoice="INV-89407", amount=31_700.00,
         account="4471", verified_accounts=["0932"], new_vendor=False, paid_before=["INV-88213"],
         observed="Settled to the verified account"),
    dict(id="RUN04", period="Week 4", vendor="Harbor Freightways", invoice="HF-5588", amount=9_800.00,
         account="1180", verified_accounts=["1180"], new_vendor=False, paid_before=["HF-5521"],
         observed="Paid on day 10; 2% discount captured"),
    dict(id="RUN05", period="Week 5", vendor="Qualis Labs", invoice="QL-0007", amount=22_000.00,
         account="3309", verified_accounts=["3309"], new_vendor=True, paid_before=[],
         observed="W-9 received before release; paid"),
    dict(id="RUN06", period="Week 6", vendor="Pinecrest Toys", invoice="INV89407", amount=31_700.00,
         account="4471", verified_accounts=["0932"], new_vendor=False, paid_before=["INV-88213", "INV-89407"],
         observed="Resubmitted invoice held; Pinecrest confirmed it was sent twice"),
    dict(id="RUN07", period="Week 7", vendor="Harbor Freightways", invoice="HF-5690", amount=140_000.00,
         account="1180", verified_accounts=["1180"], new_vendor=False, paid_before=["HF-5521", "HF-5588"],
         observed="Dual-approved; paid on day 10 with 2% discount"),
    dict(id="RUN08", period="Week 8", vendor="Novik Supply", invoice="NS-2201", amount=18_500.00,
         account="6612", verified_accounts=["6612"], new_vendor=True, paid_before=[],
         observed="W-9 on file before first payment; paid"),
    dict(id="RUN09", period="Week 9", vendor="Pinecrest Toys", invoice="INV-90112", amount=27_900.00,
         account="7720", verified_accounts=["0932"], new_vendor=False,
         paid_before=["INV-88213", "INV-89407"],
         observed="Second bank change verified by call-back before release"),
    dict(id="RUN10", period="Week 10", vendor="Harbor Freightways", invoice="HF 5588", amount=9_800.00,
         account="1180", verified_accounts=["1180"], new_vendor=False,
         paid_before=["HF-5521", "HF-5588", "HF-5690"],
         observed="Resubmitted invoice held"),
]


def normalized(invoice):
    return re.sub(r"[^A-Z0-9]", "", invoice.upper())


def is_duplicate(case):
    return normalized(case["invoice"]) in {normalized(p) for p in case["paid_before"]}


def base_terms(case):
    # The naive plan: exact-match duplicate check only, pay on the due date.
    exact_duplicate = case["invoice"] in case["paid_before"]
    return {"vendor": case["vendor"], "invoice": case["invoice"], "amount": case["amount"],
            "account": case["account"], "action": "hold" if exact_duplicate else "pay",
            "pay_day": 30, "account_verified": case["account"] in case["verified_accounts"],
            "w9_on_file": not case["new_vendor"], "dual_approval": False}


def describe(t):
    if t["action"] == "hold":
        return f"Hold {t['vendor']} {t['invoice']} (${t['amount']:,.2f}): duplicate of a paid invoice"
    text = f"Pay {t['vendor']} {t['invoice']} ${t['amount']:,.2f} on day {t['pay_day']} to account ending {t['account']}"
    return text + (", dual-approved" if t["dual_approval"] else "")


def paying(t):
    return t["action"] == "pay"


RULES = [
    Rule(
        check="duplicate-invoice", role="controls",
        violated=lambda c, t: f"{t['invoice']} matches an invoice already paid once dashes and spaces are ignored"
        if paying(t) and is_duplicate(c) else None,
        learn=lambda c, t: {"match": "normalized invoice number"},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "action": "hold"} if is_duplicate(c) else t,
        summary=lambda f: "Compare invoice numbers with dashes and spaces removed before paying",
    ),
    Rule(
        check="bank-change", role="controls",
        violated=lambda c, t: (f"Payee account changed to ending {t['account']}; policy TR-7 requires "
                               "call-back verification to a known contact")
        if paying(t) and not t["account_verified"] else None,
        learn=lambda c, t: {"vendor": c["vendor"], "account": c["account"],
                            "verified_by": "call-back to the contact in the vendor master"},
        covers=lambda c, f: c["vendor"] == f["vendor"] and c["account"] == f["account"],
        fix=lambda c, t, f: {**t, "account_verified": True},
        summary=lambda f: f"{f['vendor']} account ending {f['account']} was verified by {f['verified_by']}",
    ),
    Rule(
        check="early-pay-discount", role="treasury",
        violated=lambda c, t: (f"{c['vendor']} terms are {TERMS[c['vendor']]}; paying on day {t['pay_day']} "
                               f"forfeits ${0.02 * t['amount']:,.0f}")
        if paying(t) and TERMS[c["vendor"]].startswith("2/10") and t["pay_day"] > 10 else None,
        learn=lambda c, t: {"vendor": c["vendor"], "terms": TERMS[c["vendor"]]},
        covers=lambda c, f: c["vendor"] == f["vendor"],
        fix=lambda c, t, f: {**t, "pay_day": 10},
        summary=lambda f: f"{f['vendor']} offers {f['terms']}: pay on day 10 to take the discount",
    ),
    Rule(
        check="dual-approval", role="treasury",
        violated=lambda c, t: f"Payments above ${DUAL_APPROVAL_THRESHOLD:,} need a second treasury approver"
        if paying(t) and t["amount"] > DUAL_APPROVAL_THRESHOLD and not t["dual_approval"] else None,
        learn=lambda c, t: {"threshold": DUAL_APPROVAL_THRESHOLD},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "dual_approval": True} if t["amount"] > f["threshold"] else t,
        summary=lambda f: f"Route payments above ${f['threshold']:,} for dual approval up front",
    ),
    Rule(
        check="new-vendor-w9", role="vendor-compliance",
        violated=lambda c, t: f"{c['vendor']} is a new vendor with no W-9 on file"
        if paying(t) and not t["w9_on_file"] else None,
        learn=lambda c, t: {"requirement": "W-9 before first payment"},
        covers=lambda c, f: c["new_vendor"],
        fix=lambda c, t, f: {**t, "w9_on_file": True},
        summary=lambda f: "Request the W-9 when a new vendor's first invoice arrives, before the payment run",
    ),
]

SCENARIO = Scenario(
    title="Supplier payments, 10 weekly runs",
    workflow="supplier-payment",
    decision_prefix="PAY",
    proposer=Participant("payables-agent", "PayablesAgent"),
    reviewers=[
        Participant("controls-agent", "ControlsAgent", "controls"),
        Participant("treasury-agent", "TreasuryAgent", "treasury"),
        Participant("compliance-agent", "VendorComplianceAgent", "vendor-compliance"),
    ],
    rules=RULES,
    cases=CASES,
    base_terms=base_terms,
    describe=describe,
    subject=lambda c: f"{c['vendor']} {c['invoice']} (${c['amount']:,.2f})",
    outcome=lambda c, t: ("Payment released correctly" if paying(t) else "Duplicate held", c["observed"]),
    review_cycle_days=1,
    swap_before_round=6,
    domain_record=("PaymentRelease",
                   ["paymentId", "decisionId", "invoiceRef", "payee", "amount", "currency", "status"],
                   lambda c, t, d: (f"PMT-{c['id']}", {
                       "paymentId": f"PMT-{c['id']}", "decisionId": d, "invoiceRef": c["invoice"],
                       "payee": c["vendor"], "amount": f"{c['amount']:.2f}", "currency": "USD",
                       "status": "RELEASED" if paying(t) else "HELD"})),
)


async def run(offline: bool) -> dict:
    banner(f"{SCENARIO.title}: with institutional memory")
    with_memory = await run_loop(SCENARIO, EXAMPLE_DIR, offline, use_memory=True)
    banner(f"{SCENARIO.title}: replayed without institutional memory (control)")
    print("(same cases; the proposer ignores the shared record)")
    without = await run_loop(SCENARIO, EXAMPLE_DIR, offline, use_memory=False, verbose=False)
    return {**compare(SCENARIO, with_memory, without), "per_round": with_memory}


if __name__ == "__main__":
    args = parse_args(__doc__.strip().splitlines()[0])
    asyncio.run(run(args.offline))
