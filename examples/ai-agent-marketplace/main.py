# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
AI agent marketplace: eight sourcing decisions, and the vendor knowledge that accumulates.

An analytics team keeps buying work from AI agents on a marketplace: churn models, demand
forecasts, support-ticket triage, contract review. For each job a sourcing agent proposes the
bid with the best benchmark score. Governance, Security, Legal, the Analytics lead and
Procurement agents each enforce their rules: EU customer data stays in the EU, providers need
a current SOC 2 report, providers may not train on company data, providers whose delivered
quality fell short of their claims are excluded, and each kind of job has a price ceiling.

Every objection becomes a lesson in RetiQo: which providers are disqualified and why, which
deployments satisfy data residency, what each job type may cost, and how providers actually
performed. Before the fifth job the sourcing agent is replaced; the replacement inherits the
vendor knowledge from the shared record. The eight jobs are then replayed without memory.

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

# What the vendor-risk and legal teams know (or will find out) about each provider.
# All providers are fictional.
PROVIDERS = {
    "Brightline Analytics": {"soc2": True, "trains_on_customer_data": True},
    "Quarry Data": {"soc2": True, "trains_on_customer_data": False},
    "Meridian Insights": {"soc2": True, "trains_on_customer_data": False},
    "Solvane AI": {"soc2": False, "trains_on_customer_data": False},
}


def bids(*rows):
    return [dict(provider=p, deployment=d, price=price, benchmark=score) for p, d, price, score in rows]


CHURN_BIDS = bids(("Brightline Analytics", "global", 4800, 0.88), ("Brightline Analytics", "EU", 5200, 0.88),
                  ("Quarry Data", "global", 3900, 0.81), ("Meridian Insights", "EU", 6200, 0.86))
FORECAST_BIDS = bids(("Quarry Data", "global", 3500, 0.84), ("Brightline Analytics", "global", 4600, 0.83),
                     ("Meridian Insights", "EU", 6000, 0.82))
TRIAGE_BIDS = bids(("Solvane AI", "EU", 2200, 0.90), ("Brightline Analytics", "global", 3100, 0.87),
                   ("Brightline Analytics", "EU", 3400, 0.87), ("Meridian Insights", "EU", 4100, 0.85))
CONTRACT_BIDS = bids(("Meridian Insights", "EU", 4500, 0.91), ("Solvane AI", "EU", 1900, 0.89),
                     ("Brightline Analytics", "EU", 2900, 0.87), ("Brightline Analytics", "global", 2600, 0.87))

# How providers actually performed on earlier jobs, as recorded in their Outcomes.
QUARRY_SHORTFALL = {"Quarry Data": {"claimed": 0.84, "delivered": 0.71}}

CASES = [
    dict(id="JOB-Q1-CHURN", period="Q1 2026", task="churn model", eu_data=True, bids=CHURN_BIDS,
         ceiling=None, history={}, observed="Delivered 0.89 AUC from the EU deployment"),
    dict(id="JOB-Q1-FORECAST", period="Q1 2026", task="demand forecast", eu_data=False, bids=FORECAST_BIDS,
         ceiling=None, history={}, observed="Quarry delivered 0.71 accuracy against a claimed 0.84"),
    dict(id="JOB-Q2-TRIAGE", period="Q2 2026", task="ticket triage", eu_data=True, bids=TRIAGE_BIDS,
         ceiling=None, history=QUARRY_SHORTFALL, observed="Triage accuracy 0.88; no data left the EU"),
    dict(id="JOB-Q2-FORECAST", period="Q2 2026", task="demand forecast", eu_data=False, bids=FORECAST_BIDS,
         ceiling=None, history=QUARRY_SHORTFALL, observed="Brightline delivered 0.84 accuracy"),
    dict(id="JOB-Q3-CHURN", period="Q3 2026", task="churn model", eu_data=True, bids=CHURN_BIDS,
         ceiling=None, history=QUARRY_SHORTFALL, observed="Delivered 0.90 AUC"),
    dict(id="JOB-Q3-CONTRACTS", period="Q3 2026", task="contract review", eu_data=True, bids=CONTRACT_BIDS,
         ceiling=3000, history=QUARRY_SHORTFALL, observed="Reviewed 1,200 contracts under the ceiling"),
    dict(id="JOB-Q4-TRIAGE", period="Q4 2026", task="ticket triage", eu_data=True, bids=TRIAGE_BIDS,
         ceiling=None, history=QUARRY_SHORTFALL, observed="Triage accuracy 0.89"),
    dict(id="JOB-Q4-FORECAST", period="Q4 2026", task="demand forecast", eu_data=False, bids=FORECAST_BIDS,
         ceiling=None, history=QUARRY_SHORTFALL, observed="Brightline delivered 0.85 accuracy"),
]


def select(case, constraints):
    """Best benchmark among bids that satisfy what we know so far."""
    options = [
        b for b in case["bids"]
        if b["provider"] not in constraints["excluded"]
        and (b["deployment"] == "EU" or not constraints["require_eu"])
        and (constraints["max_price"] is None or b["price"] <= constraints["max_price"])
    ]
    best = max(options, key=lambda b: (b["benchmark"], -b["price"]))
    return {**constraints, **best}


def base_terms(case):
    return select(case, {"excluded": [], "require_eu": False, "max_price": None, "training_opt_out": False})


def describe(t):
    text = f"{t['provider']} ({t['deployment']} deployment), ${t['price']:,}, benchmark {t['benchmark']:.2f}"
    if t["training_opt_out"] and PROVIDERS[t["provider"]]["trains_on_customer_data"]:
        text += ", with training opt-out addendum"
    return text


def exclude(case, terms, provider):
    return select(case, {**terms, "excluded": sorted(set(terms["excluded"]) | {provider})})


RULES = [
    Rule(
        check="data-residency", role="governance",
        violated=lambda c, t: f"{c['task']} uses EU customer records; the {t['deployment']} deployment processes them outside the EU"
        if c["eu_data"] and t["deployment"] != "EU" else None,
        learn=lambda c, t: {"data": "EU customer records"},
        covers=lambda c, f: c["eu_data"],
        fix=lambda c, t, f: select(c, {**t, "require_eu": True}),
        summary=lambda f: "Jobs using EU customer records must use an EU deployment",
    ),
    Rule(
        check="security-soc2", role="security",
        violated=lambda c, t: f"{t['provider']} has no current SOC 2 Type II report"
        if not PROVIDERS[t["provider"]]["soc2"] else None,
        learn=lambda c, t: {"provider": t["provider"]},
        covers=lambda c, f: any(b["provider"] == f["provider"] for b in c["bids"]),
        fix=lambda c, t, f: exclude(c, t, f["provider"]),
        summary=lambda f: f"{f['provider']} is disqualified until it has a SOC 2 Type II report",
    ),
    Rule(
        check="delivered-quality", role="analytics-lead",
        violated=lambda c, t: (f"{t['provider']} delivered {c['history'][t['provider']]['delivered']:.2f} "
                               f"against a claimed {c['history'][t['provider']]['claimed']:.2f} last time")
        if t["provider"] in c["history"] else None,
        learn=lambda c, t: {"provider": t["provider"], **c["history"][t["provider"]]},
        covers=lambda c, f: True,
        fix=lambda c, t, f: exclude(c, t, f["provider"]) if t["provider"] == f["provider"] else t,
        summary=lambda f: (f"{f['provider']} over-claims: delivered {f['delivered']:.2f} vs {f['claimed']:.2f} "
                           "claimed; do not select on its benchmark"),
    ),
    Rule(
        check="price-ceiling", role="procurement",
        violated=lambda c, t: f"{c['task']} jobs are capped at ${c['ceiling']:,}; this bid is ${t['price']:,}"
        if c["ceiling"] and t["price"] > c["ceiling"] else None,
        learn=lambda c, t: {"task": c["task"], "ceiling": c["ceiling"]},
        covers=lambda c, f: c["task"] == f["task"],
        fix=lambda c, t, f: select(c, {**t, "max_price": f["ceiling"]}),
        summary=lambda f: f"{f['task'].capitalize()} jobs are capped at ${f['ceiling']:,}",
    ),
    Rule(
        check="training-opt-out", role="legal",
        violated=lambda c, t: f"{t['provider']}'s standard terms let it train on our data; the opt-out addendum is required"
        if PROVIDERS[t["provider"]]["trains_on_customer_data"] and not t["training_opt_out"] else None,
        learn=lambda c, t: {"provider": t["provider"]},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "training_opt_out": True} if t["provider"] == f["provider"] else t,
        summary=lambda f: f"Contract {f['provider']} only with the training opt-out addendum",
    ),
]

SCENARIO = Scenario(
    title="AI service sourcing, 8 jobs",
    workflow="provider-selection",
    decision_prefix="SOURCE",
    proposer=Participant("sourcing-agent", "SourcingAgent"),
    reviewers=[
        Participant("governance-agent", "GovernanceAgent", "governance"),
        Participant("security-agent", "SecurityAgent", "security"),
        Participant("analytics-lead-agent", "AnalyticsLeadAgent", "analytics-lead"),
        Participant("procurement-agent", "ProcurementAgent", "procurement"),
        Participant("legal-agent", "LegalAgent", "legal"),
    ],
    rules=RULES,
    cases=CASES,
    base_terms=base_terms,
    describe=describe,
    subject=lambda c: f"Provider for {c['task']} ({c['id']})",
    outcome=lambda c, t: (f"{t['provider']} delivers at or near benchmark {t['benchmark']:.2f}", c["observed"]),
    review_cycle_days=2,
    swap_before_round=5,
    domain_record=("ServiceAgreement", ["agreementId", "decisionId", "provider", "serviceType", "price", "status"],
                   lambda c, t, d: (f"AGR-{c['id']}", {
                       "agreementId": f"AGR-{c['id']}", "decisionId": d,
                       "provider": f"{t['provider']} ({t['deployment']})", "serviceType": c["task"],
                       "price": str(t["price"]), "status": "ACTIVE"})),
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
