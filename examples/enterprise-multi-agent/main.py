# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Enterprise multi-agent: eight quarters of inventory reorders, and what the organization learns.

A procurement agent proposes a quarterly reorder of an industrial sensor. Inventory, Quality,
Vendor Management and Finance agents each enforce their own rules: stock already on order,
suppliers on quality hold, supplier minimum order quantities, the year-end spending freeze,
and competitive quotes for large orders.

Every objection becomes a lesson in RetiQo. Each quarter the proposer applies every lesson
that covers the new situation before proposing, so objections that happened once stop
recurring. Before quarter five the procurement agent is replaced by a new model; it catches
up from the shared record and keeps improving. The same eight quarters are then replayed
without institutional memory for comparison.

    python main.py --offline      # in-process simulation, no RetiQo host needed
    python main.py                # against the RetiQo host configured in .env
"""
import asyncio
import math
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR.parent))

from common import banner, parse_args  # noqa: E402
from common.loop import Participant, Rule, Scenario, compare, run_loop  # noqa: E402

SKU = "SKU-7731 industrial pressure sensor"
QUOTE_THRESHOLD = 15_000

SUPPLIERS = {
    "Northgate Components": {"price": 10.00, "moq": 200},
    "Corvale Parts": {"price": 9.40, "moq": 500},
    "Brandt Electronics": {"price": 10.60, "moq": 100},
}

# Eight quarters of real-world conditions. New kinds of problems appear over time;
# some come back (a supplier returns to quality hold, the freeze recurs every year-end).
CASES = [
    dict(id="2026Q1", period="Q1 2026", forecast=900, on_hand=150, inbound=400,
         default="Northgate Components", holds=[], freeze_cap=None, cost_per_day=1_200,
         observed="Received on time; closed the quarter with 40 units spare"),
    dict(id="2026Q2", period="Q2 2026", forecast=1000, on_hand=100, inbound=0,
         default="Northgate Components", holds=["Northgate Components"], freeze_cap=None,
         cost_per_day=1_500, observed="Corvale lot passed incoming inspection"),
    dict(id="2026Q3", period="Q3 2026", forecast=1100, on_hand=200, inbound=300,
         default="Northgate Components", holds=["Northgate Components"], freeze_cap=None,
         cost_per_day=1_500, observed="Received on time; no overstock"),
    dict(id="2026Q4", period="Q4 2026", forecast=1400, on_hand=100, inbound=300,
         default="Northgate Components", holds=["Northgate Components"], freeze_cap=5_000,
         cost_per_day=2_000, observed="First delivery within the freeze cap; balance shipped in January"),
    dict(id="2027Q1", period="Q1 2027", forecast=800, on_hand=120, inbound=0,
         default="Northgate Components", holds=[], freeze_cap=5_000, cost_per_day=1_200,
         observed="Northgate hold lifted; order split across the freeze"),
    dict(id="2027Q2", period="Q2 2027", forecast=2000, on_hand=100, inbound=250,
         default="Northgate Components", holds=[], freeze_cap=None, cost_per_day=2_500,
         observed="Demand spike covered; quotes saved 3% on the award"),
    dict(id="2027Q3", period="Q3 2027", forecast=700, on_hand=150, inbound=500,
         default="Brandt Electronics", holds=[], freeze_cap=None, cost_per_day=800,
         observed="Small top-up order from Brandt while Northgate is at capacity"),
    dict(id="2027Q4", period="Q4 2027", forecast=1600, on_hand=100, inbound=200,
         default="Northgate Components", holds=["Northgate Components"], freeze_cap=5_000,
         cost_per_day=2_000, observed="New Northgate hold handled without a review cycle"),
]


def priced(terms):
    terms = dict(terms)
    terms["unit_price"] = SUPPLIERS[terms["supplier"]]["price"]
    terms["total"] = round(terms["qty"] * terms["unit_price"], 2)
    return terms


def base_terms(case):
    return priced({"supplier": case["default"], "qty": case["forecast"] - case["on_hand"],
                   "deferred": 0, "quotes": 1})


def describe(terms):
    text = f"{terms['qty']} units from {terms['supplier']} at ${terms['unit_price']:.2f} (${terms['total']:,.0f})"
    if terms.get("deferred"):
        text += f", {terms['deferred']} more deferred to next quarter"
    if terms.get("quotes", 1) > 1:
        text += f", {terms['quotes']} competing quotes attached"
    return text


def need(case):
    return case["forecast"] - case["on_hand"] - case["inbound"]


def cheapest_available(case, exclude):
    options = [s for s in SUPPLIERS if s not in case["holds"] and s != exclude]
    return min(options, key=lambda s: SUPPLIERS[s]["price"])


RULES = [
    Rule(
        check="inbound-orders", role="inventory",
        # Rounding up to a supplier's minimum order is not overstock.
        violated=lambda c, t: (f"{c['inbound']} units are already inbound on open POs; "
                               f"this overstocks by {t['qty'] + t['deferred'] - need(c)}")
        if c["inbound"] and t["qty"] + t["deferred"] > max(need(c), SUPPLIERS[t["supplier"]]["moq"]) else None,
        learn=lambda c, t: {},
        covers=lambda c, f: True,
        fix=lambda c, t, f: priced({**t, "qty": min(t["qty"], need(c)),
                                    "deferred": max(0, min(t["deferred"], need(c) - t["qty"]))}),
        summary=lambda f: "Subtract units already inbound on open POs before sizing a reorder",
    ),
    Rule(
        check="quality-hold", role="quality",
        violated=lambda c, t: f"{t['supplier']} is on quality hold (open nonconformance report)"
        if t["supplier"] in c["holds"] else None,
        learn=lambda c, t: {"supplier": t["supplier"], "alternate": cheapest_available(c, t["supplier"])},
        covers=lambda c, f: f["supplier"] in c["holds"],
        fix=lambda c, t, f: priced({**t, "supplier": f["alternate"]}) if t["supplier"] == f["supplier"] else t,
        summary=lambda f: f"When {f['supplier']} is on quality hold, order from {f['alternate']}",
    ),
    Rule(
        check="supplier-moq", role="vendor-management",
        violated=lambda c, t: (f"{t['supplier']} has a minimum order of "
                               f"{SUPPLIERS[t['supplier']]['moq']} units")
        if 0 < t["qty"] < SUPPLIERS[t["supplier"]]["moq"] else None,
        learn=lambda c, t: {"supplier": t["supplier"], "moq": SUPPLIERS[t["supplier"]]["moq"]},
        covers=lambda c, f: True,
        fix=lambda c, t, f: priced({**t, "qty": max(t["qty"], f["moq"])})
        if t["supplier"] == f["supplier"] and 0 < t["qty"] < f["moq"] else t,
        summary=lambda f: f"{f['supplier']} has a minimum order of {f['moq']} units",
    ),
    Rule(
        check="spending-freeze", role="finance",
        violated=lambda c, t: f"Year-end spending freeze caps new orders at ${c['freeze_cap']:,}"
        if c["freeze_cap"] and t["total"] > c["freeze_cap"] else None,
        learn=lambda c, t: {"cap": c["freeze_cap"]},
        covers=lambda c, f: bool(c["freeze_cap"]),
        fix=lambda c, t, f: _split_for_cap(t, c["freeze_cap"] or f["cap"]),
        summary=lambda f: f"During the year-end freeze (Q4-Q1), split orders to stay under ${f['cap']:,}",
    ),
    Rule(
        check="competitive-quotes", role="finance",
        violated=lambda c, t: f"Orders above ${QUOTE_THRESHOLD:,} need two competing quotes on file"
        if t["total"] > QUOTE_THRESHOLD and t.get("quotes", 1) < 2 else None,
        learn=lambda c, t: {"threshold": QUOTE_THRESHOLD},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "quotes": 2} if t["total"] > f["threshold"] else t,
        summary=lambda f: f"Attach two competing quotes to any order above ${f['threshold']:,}",
    ),
]


def _split_for_cap(terms, cap):
    if terms["total"] <= cap:
        return terms
    now = math.floor(cap / terms["unit_price"])
    return priced({**terms, "qty": now, "deferred": terms["deferred"] + terms["qty"] - now})


SCENARIO = Scenario(
    title="Inventory replenishment, 8 quarters",
    workflow="inventory-reorder",
    decision_prefix="REORDER",
    proposer=Participant("procurement-agent", "ProcurementAgent"),
    reviewers=[
        Participant("inventory-agent", "InventoryAgent", "inventory"),
        Participant("quality-agent", "QualityAgent", "quality"),
        Participant("vendor-agent", "VendorManagementAgent", "vendor-management"),
        Participant("finance-agent", "FinanceAgent", "finance"),
    ],
    rules=RULES,
    cases=CASES,
    base_terms=base_terms,
    describe=describe,
    subject=lambda c: f"Reorder {SKU}, {c['period']}",
    outcome=lambda c, t: (f"{t['qty'] + t['deferred']} units to cover {c['period']}", c["observed"]),
    review_cycle_days=3,
    swap_before_round=5,
    domain_record=("PurchaseOrder",
                   ["orderId", "decisionId", "supplier", "sku", "quantity", "unitPrice", "status"],
                   lambda c, t, d: (f"PO-{c['id']}", {
                       "orderId": f"PO-{c['id']}", "decisionId": d, "supplier": t["supplier"],
                       "sku": "SKU-7731", "quantity": str(t["qty"]),
                       "unitPrice": f"{t['unit_price']:.2f}", "status": "PLACED"})),
    delay_cost_label="stockout exposure while waiting for approval",
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
