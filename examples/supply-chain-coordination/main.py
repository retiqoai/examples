# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Supply chain: eight shipment exceptions, and the playbook the organization builds from them.

When a shipment is delayed (a customs hold, port congestion, a border backlog), a logistics
agent proposes a recovery plan: usually air-freighting the pallets the customer needs first.
Quality, Trade Compliance, Safety, Finance and Customer Service agents each enforce their
rules: cold-chain qualified carriers for temperature-sensitive lots, cargo-only aircraft for
lithium batteries, lane-specific customs documents, a cost justification for large
expedites, and proactive notice to key accounts.

Every objection becomes a lesson in RetiQo. Each new exception starts from all of them, so
the time a customer's line waits on internal review shrinks as the playbook grows. Before
the fifth exception the logistics agent is replaced; the replacement inherits the playbook
from the shared record. The eight exceptions are then replayed without memory.

    python main.py --offline      # in-process simulation, no RetiQo host needed
    python main.py                # against the RetiQo host configured in .env
"""
import asyncio
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE_DIR.parent))

from common import banner, parse_args  # noqa: E402
from common.loop import Participant, Rule, Scenario, compare, run_loop  # noqa: E402

EXPEDITE_JUSTIFICATION_THRESHOLD = 15_000

CARRIERS = {
    # USD per pallet; passenger-belly capacity cannot carry lithium batteries.
    "Swiftjet Cargo": {"rate": 700, "cold_chain": False, "cargo_only": False},
    "Meridian Air Freight": {"rate": 720, "cold_chain": False, "cargo_only": True},
    "Coldline Air": {"rate": 770, "cold_chain": True, "cargo_only": True},
}

LANE_DOCUMENTS = {
    "MTY-DAL": "Carta Porte and USMCA certificate of origin",
}

# Eight exceptions over two quarters. `penalty_per_day` is what the customer charges for
# each day their line is short of parts. All companies and orders are fictional.
CASES = [
    dict(id="ORD-5510", period="Jan 12", customer="Halden Manufacturing", key_account=True,
         lane="RTM-ORD", cause="customs hold, 6 days", pallets=30, temperature_sensitive=True,
         commodity="adhesives", cost_per_day=15_000,
         observed="Air pallets arrived in 2 days; Halden's line never stopped"),
    dict(id="ORD-5560", period="Jan 29", customer="Halden Manufacturing", key_account=True,
         lane="SZX-LAX", cause="port congestion, 5 days", pallets=24, temperature_sensitive=False,
         commodity="lithium batteries", cost_per_day=15_000,
         observed="Cargo-only flight booked; batteries arrived in 3 days"),
    dict(id="ORD-5601", period="Feb 10", customer="Aldermoor Foods", key_account=False,
         lane="MTY-DAL", cause="border backlog, 3 days", pallets=12, temperature_sensitive=True,
         commodity="dairy ingredients", cost_per_day=4_000,
         observed="Cleared the border with complete documents on the first attempt"),
    dict(id="ORD-5620", period="Feb 24", customer="Halden Manufacturing", key_account=True,
         lane="RTM-ORD", cause="customs hold, 4 days", pallets=20, temperature_sensitive=True,
         commodity="adhesives", cost_per_day=15_000,
         observed="Recovered in 2 days using the established plan"),
    dict(id="ORD-5655", period="Mar 9", customer="Aldermoor Foods", key_account=False,
         lane="MTY-DAL", cause="border backlog, 4 days", pallets=10, temperature_sensitive=True,
         commodity="dairy ingredients", cost_per_day=4_000,
         observed="Documents ready before the truck reached the border"),
    dict(id="ORD-5690", period="Mar 23", customer="Vantor Medical", key_account=True,
         lane="RTM-BOS", cause="customs hold, 5 days", pallets=40, temperature_sensitive=True,
         commodity="reagents", cost_per_day=20_000,
         observed="Vantor notified within the hour; reagents arrived in 2 days"),
    dict(id="ORD-5712", period="Apr 6", customer="Halden Manufacturing", key_account=True,
         lane="SZX-LAX", cause="port congestion, 6 days", pallets=28, temperature_sensitive=False,
         commodity="lithium batteries", cost_per_day=15_000,
         observed="Cargo-only flight booked the same day"),
    dict(id="ORD-5740", period="Apr 20", customer="Vantor Medical", key_account=True,
         lane="SZX-BOS", cause="port congestion, 5 days", pallets=18, temperature_sensitive=True,
         commodity="lithium-powered monitors", cost_per_day=20_000,
         observed="Cold-chain, cargo-only flight; arrived in 3 days"),
]


def lithium(case):
    return "lithium" in case["commodity"]


def priced(terms, case):
    terms = dict(terms)
    terms["cost"] = case["pallets"] * CARRIERS[terms["carrier"]]["rate"]
    return terms


def base_terms(case):
    return priced({"carrier": "Swiftjet Cargo", "documents": [], "cost_justification": False,
                   "customer_notified": False}, case)


def describe(t):
    text = f"Air-freight the critical pallets via {t['carrier']} (${t['cost']:,})"
    extras = []
    if t["documents"]:
        extras.append("with " + ", ".join(t["documents"]))
    if t["cost_justification"]:
        extras.append("penalty-avoidance case attached")
    if t["customer_notified"]:
        extras.append("customer notified with new ETA")
    return text + (f"; {'; '.join(extras)}" if extras else "")


def cheapest(case, cold_chain=False, cargo_only=False):
    options = [c for c, v in CARRIERS.items()
               if (v["cold_chain"] or not cold_chain) and (v["cargo_only"] or not cargo_only)]
    return min(options, key=lambda c: CARRIERS[c]["rate"])


def needs(case):
    return dict(cold_chain=case["temperature_sensitive"], cargo_only=lithium(case))


RULES = [
    Rule(
        check="cold-chain-carrier", role="quality",
        violated=lambda c, t: f"{t['carrier']} is not qualified for temperature-sensitive {c['commodity']}"
        if c["temperature_sensitive"] and not CARRIERS[t["carrier"]]["cold_chain"] else None,
        learn=lambda c, t: {"requirement": "cold-chain qualified carrier"},
        covers=lambda c, f: c["temperature_sensitive"],
        fix=lambda c, t, f: priced({**t, "carrier": cheapest(c, **needs(c))}, c)
        if not CARRIERS[t["carrier"]]["cold_chain"] else t,
        summary=lambda f: "Temperature-sensitive lots fly only with a cold-chain qualified carrier (Coldline Air)",
    ),
    Rule(
        check="lithium-cargo-only", role="safety",
        violated=lambda c, t: f"{t['carrier']} uses passenger aircraft; lithium batteries must fly cargo-only"
        if lithium(c) and not CARRIERS[t["carrier"]]["cargo_only"] else None,
        learn=lambda c, t: {"commodity": "lithium batteries"},
        covers=lambda c, f: lithium(c),
        fix=lambda c, t, f: priced({**t, "carrier": cheapest(c, **needs(c))}, c)
        if not CARRIERS[t["carrier"]]["cargo_only"] else t,
        summary=lambda f: "Anything containing lithium batteries must fly cargo-only",
    ),
    Rule(
        check="lane-documents", role="trade-compliance",
        violated=lambda c, t: f"Lane {c['lane']} needs {LANE_DOCUMENTS[c['lane']]} before the truck reaches the border"
        if c["lane"] in LANE_DOCUMENTS and LANE_DOCUMENTS[c["lane"]] not in t["documents"] else None,
        learn=lambda c, t: {"lane": c["lane"], "documents": LANE_DOCUMENTS[c["lane"]]},
        covers=lambda c, f: c["lane"] == f["lane"],
        fix=lambda c, t, f: {**t, "documents": t["documents"] + [f["documents"]]}
        if f["documents"] not in t["documents"] else t,
        summary=lambda f: f"Lane {f['lane']} needs {f['documents']} prepared up front",
    ),
    Rule(
        check="expedite-justification", role="finance",
        violated=lambda c, t: (f"Expedite cost ${t['cost']:,} is above ${EXPEDITE_JUSTIFICATION_THRESHOLD:,}; "
                               "attach the penalty-avoidance calculation")
        if t["cost"] > EXPEDITE_JUSTIFICATION_THRESHOLD and not t["cost_justification"] else None,
        learn=lambda c, t: {"threshold": EXPEDITE_JUSTIFICATION_THRESHOLD},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "cost_justification": True} if t["cost"] > f["threshold"] else t,
        summary=lambda f: f"Attach the penalty-avoidance calculation to any expedite above ${f['threshold']:,}",
    ),
    Rule(
        check="key-account-notice", role="customer-service",
        violated=lambda c, t: f"{c['customer']} is a key account; they must hear about the delay from us, with a new ETA"
        if c["key_account"] and not t["customer_notified"] else None,
        learn=lambda c, t: {"customer": c["customer"]},
        covers=lambda c, f: c["customer"] == f["customer"],
        fix=lambda c, t, f: {**t, "customer_notified": True},
        summary=lambda f: f"{f['customer']} is a key account: notify them with a new ETA as part of the plan",
    ),
]

SCENARIO = Scenario(
    title="Shipment exceptions, 8 incidents",
    workflow="shipment-exception",
    decision_prefix="EXCEPTION",
    proposer=Participant("logistics-agent", "LogisticsAgent"),
    reviewers=[
        Participant("quality-agent", "QualityAgent", "quality"),
        Participant("safety-agent", "SafetyAgent", "safety"),
        Participant("trade-compliance-agent", "TradeComplianceAgent", "trade-compliance"),
        Participant("finance-agent", "FinanceAgent", "finance"),
        Participant("customer-service-agent", "CustomerServiceAgent", "customer-service"),
    ],
    rules=RULES,
    cases=CASES,
    base_terms=base_terms,
    describe=describe,
    subject=lambda c: f"{c['customer']} {c['id']}, {c['lane']}: {c['cause']}",
    outcome=lambda c, t: ("Customer line keeps running", c["observed"]),
    review_cycle_days=1,
    swap_before_round=5,
    domain_record=("Shipment", ["shipmentId", "orderId", "decisionId", "carrier", "eta", "status"],
                   lambda c, t, d: (f"SHP-{c['id']}-AIR", {
                       "shipmentId": f"SHP-{c['id']}-AIR", "orderId": c["id"], "decisionId": d,
                       "carrier": t["carrier"], "eta": "2-3 days", "status": "BOOKED"})),
    delay_cost_label="customer line-stoppage penalties while the plan waited on review",
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
