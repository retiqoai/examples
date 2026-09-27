# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Options hedging: ten weekly hedge decisions on a trading desk, and the desk knowledge that builds up.

A trading agent protects a long equity position each week by buying put options. Risk,
Volatility, Execution and Compliance agents each enforce the desk's rules: size the hedge
by option delta (not by notional), avoid paying inflated implied volatility ahead of
earnings, trade expiries that are actually liquid, never trade a name on the restricted
list, and size proxy hedges by beta.

Every objection becomes a lesson in RetiQo: a sizing method, a volatility playbook, which
names have unusable weekly options, which names are restricted and which index to use
instead, and at what beta. Before week five the trading agent is replaced; the replacement
inherits the desk's knowledge from the shared record. The ten weeks are then replayed
without institutional memory.

Illustrative only: tickers are fictional and the option model is deliberately simple
(fixed deltas and premiums). This is a demonstration of the learning loop, not trading
advice.

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

# Simplified one-month option model: a 97% put and a 97/87 put spread.
STRUCTURES = {
    "97% put": {"delta": 0.40, "premium_pct": 2.0},
    "97/87 put spread": {"delta": 0.28, "premium_pct": 1.0},
}
EVENT_VOL_MULTIPLIER = 1.5     # long puts cost more when implied volatility is elevated
IV_RANK_EXPENSIVE = 80
MAX_WEEKLY_SPREAD_PCT = 5.0
HEDGE_RATIO = 0.50             # desk policy: offset half of the position's delta
HEDGE_TOLERANCE = 0.05         # ... give or take 5 percentage points

# Fictional underlyings. `beta` is the name's beta to its sector index proxy.
NAMES = {
    "ARVN": {"company": "Arven Robotics", "proxy": None, "beta": 1.0},
    "HLVS": {"company": "Halvard Semiconductor", "proxy": "SMIX", "beta": 1.3},
    "KSTL": {"company": "Kestrel Logistics", "proxy": None, "beta": 1.0},
    "SMIX": {"company": "semiconductor sector index fund", "proxy": None, "beta": 1.0},
}
SPOT = {"ARVN": 120.0, "HLVS": 80.0, "KSTL": 45.0, "SMIX": 250.0}
WEEKLY_SPREAD_PCT = {"ARVN": 2.0, "HLVS": 9.0, "KSTL": 12.0, "SMIX": 1.0}


def week(n, name, shares, iv_rank, event=None, restricted=(), observed=""):
    return dict(id=f"W{n:02d}", period=f"Week {n}", name=name, shares=shares, iv_rank=iv_rank,
                event=event, restricted=list(restricted), observed=observed,
                # value at risk on the position for each day it waits unhedged (2% daily move)
                cost_per_day=round(shares * SPOT[name] * 0.02))


CASES = [
    week(1, "ARVN", 50_000, 40, observed="Hedge held ARVN's 6% drawdown to a 0.5% loss"),
    week(2, "ARVN", 50_000, 88, event="earnings in 5 days",
         observed="IV fell from 62% to 38% after earnings; the spread kept its value"),
    week(3, "HLVS", 100_000, 50, observed="Monthly puts filled at a 1.2% spread"),
    week(4, "ARVN", 60_000, 45, observed="Routine roll; no issues"),
    week(5, "HLVS", 100_000, 55, restricted=["HLVS"],
         observed="Proxy hedge tracked HLVS within 4% while the firm advised on its acquisition"),
    week(6, "ARVN", 60_000, 91, event="earnings in 3 days", observed="Post-earnings IV crush absorbed by the spread"),
    week(7, "HLVS", 120_000, 60, restricted=["HLVS"], observed="Proxy hedge held through the restriction"),
    week(8, "KSTL", 200_000, 83, event="central bank meeting in 4 days",
         observed="Monthly spread filled; weeklies were quoted 12% wide"),
    week(9, "HLVS", 100_000, 86, event="earnings in 6 days",
         observed="Restriction lifted; earnings hedged with a monthly put spread"),
    week(10, "KSTL", 150_000, 35, observed="Routine hedge; no issues"),
]


def exposure_in(case, underlying, beta_adjusted):
    """Position size expressed in shares of the hedge underlying."""
    beta = NAMES[case["name"]]["beta"] if underlying != case["name"] and beta_adjusted else 1.0
    return case["shares"] * SPOT[case["name"]] * beta / SPOT[underlying]


def sized(case, terms):
    terms = dict(terms)
    shares_equivalent = exposure_in(case, terms["underlying"], terms["beta_adjusted"])
    delta = STRUCTURES[terms["structure"]]["delta"] if terms["delta_sized"] else 1.0
    ratio = HEDGE_RATIO if terms["delta_sized"] else 1.0
    terms["contracts"] = round(shares_equivalent * ratio / 100 / delta)
    premium = STRUCTURES[terms["structure"]]["premium_pct"] / 100
    if terms["structure"] == "97% put" and case["event"] and case["iv_rank"] >= IV_RANK_EXPENSIVE:
        premium *= EVENT_VOL_MULTIPLIER
    terms["cost"] = round(terms["contracts"] * 100 * SPOT[terms["underlying"]] * premium)
    return terms


def coverage(case, terms):
    """Fraction of the position's true (beta-adjusted) delta the hedge offsets."""
    true_exposure = exposure_in(case, terms["underlying"], beta_adjusted=True)
    return terms["contracts"] * 100 * STRUCTURES[terms["structure"]]["delta"] / true_exposure


def base_terms(case):
    # The naive plan: weekly 97% puts on the name itself, contracts matched to notional.
    return sized(case, {"underlying": case["name"], "structure": "97% put", "expiry": "weekly",
                        "delta_sized": False, "beta_adjusted": False})


def describe(t):
    return (f"Buy {t['contracts']:,} {t['underlying']} {t['expiry']} {t['structure']} "
            f"(premium ${t['cost']:,})")


RULES = [
    Rule(
        check="restricted-list", role="compliance",
        violated=lambda c, t: (f"{t['underlying']} is on the restricted list (the firm is advising on a transaction); "
                               "no trading in its securities or options")
        if t["underlying"] in c["restricted"] else None,
        learn=lambda c, t: {"name": c["name"], "proxy": NAMES[c["name"]]["proxy"]},
        covers=lambda c, f: c["name"] == f["name"] and f["name"] in c["restricted"],
        fix=lambda c, t, f: sized(c, {**t, "underlying": f["proxy"]}) if t["underlying"] == f["name"] else t,
        summary=lambda f: f"While {f['name']} is restricted, hedge it with {f['proxy']} options instead",
    ),
    Rule(
        check="proxy-beta", role="risk",
        violated=lambda c, t: (f"{t['underlying']} hedge for {c['name']} ignores beta "
                               f"{NAMES[c['name']]['beta']}; it covers {coverage(c, t):.0%} of the risk")
        if t["underlying"] != c["name"] and not t["beta_adjusted"] else None,
        learn=lambda c, t: {"name": c["name"], "proxy": t["underlying"], "beta": NAMES[c["name"]]["beta"]},
        covers=lambda c, f: c["name"] == f["name"],
        fix=lambda c, t, f: sized(c, {**t, "beta_adjusted": True}) if t["underlying"] == f["proxy"] else t,
        summary=lambda f: f"Size {f['proxy']} hedges for {f['name']} at beta {f['beta']}",
    ),
    Rule(
        check="delta-sizing", role="risk",
        violated=lambda c, t: (f"Contracts matched to notional offset {coverage(c, t):.0%} of the position's delta; "
                               f"the desk target is {HEDGE_RATIO - HEDGE_TOLERANCE:.0%}-{HEDGE_RATIO + HEDGE_TOLERANCE:.0%}")
        if not t["delta_sized"] else None,
        learn=lambda c, t: {"method": "target delta / option delta", "target": HEDGE_RATIO},
        covers=lambda c, f: True,
        fix=lambda c, t, f: sized(c, {**t, "delta_sized": True}),
        summary=lambda f: ("Size hedges by option delta, not by notional: "
                           "contracts = target delta / (100 x option delta)"),
    ),
    Rule(
        check="event-volatility", role="volatility",
        violated=lambda c, t: (f"Implied volatility is at the {c['iv_rank']}th percentile with {c['event']}; "
                               "outright puts will lose value when it falls after the event")
        if c["event"] and c["iv_rank"] >= IV_RANK_EXPENSIVE and t["structure"] == "97% put" else None,
        learn=lambda c, t: {"iv_rank_min": IV_RANK_EXPENSIVE},
        covers=lambda c, f: bool(c["event"]) and c["iv_rank"] >= f["iv_rank_min"],
        fix=lambda c, t, f: sized(c, {**t, "structure": "97/87 put spread"}),
        summary=lambda f: (f"Before a scheduled event with IV rank {f['iv_rank_min']}+, use a 97/87 put spread: "
                           "the short put offsets the inflated volatility"),
    ),
    Rule(
        check="option-liquidity", role="execution",
        violated=lambda c, t: (f"{t['underlying']} weekly options trade {WEEKLY_SPREAD_PCT[t['underlying']]:.0f}% wide; "
                               "the hedge would lose that on entry")
        if t["expiry"] == "weekly" and WEEKLY_SPREAD_PCT[t["underlying"]] > MAX_WEEKLY_SPREAD_PCT else None,
        learn=lambda c, t: {"underlying": t["underlying"], "spread_pct": WEEKLY_SPREAD_PCT[t["underlying"]]},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "expiry": "monthly"} if t["underlying"] == f["underlying"] else t,
        summary=lambda f: f"Use monthly expiries on {f['underlying']}; its weeklies trade {f['spread_pct']:.0f}% wide",
    ),
]

SCENARIO = Scenario(
    title="Options hedging, 10 weeks",
    workflow="equity-hedge",
    decision_prefix="HEDGE",
    proposer=Participant("trading-agent", "TradingAgent"),
    reviewers=[
        Participant("compliance-agent", "ComplianceAgent", "compliance"),
        Participant("risk-agent", "RiskAgent", "risk"),
        Participant("volatility-agent", "VolatilityAgent", "volatility"),
        Participant("execution-agent", "ExecutionAgent", "execution"),
    ],
    rules=RULES,
    cases=CASES,
    base_terms=base_terms,
    describe=describe,
    subject=lambda c: (f"Hedge {c['shares']:,} {c['name']} ({NAMES[c['name']]['company']})"
                       + (f", {c['event']}" if c["event"] else "")),
    outcome=lambda c, t: (f"Position delta {coverage(c, t):.0%} hedged", c["observed"]),
    review_cycle_days=1,
    swap_before_round=5,
    domain_record=("HedgeOrder", ["orderId", "decisionId", "underlying", "structure", "expiry", "contracts", "status"],
                   lambda c, t, d: (f"HO-{c['id']}", {
                       "orderId": f"HO-{c['id']}", "decisionId": d, "underlying": t["underlying"],
                       "structure": t["structure"], "expiry": t["expiry"],
                       "contracts": str(t["contracts"]), "status": "WORKING"})),
    delay_cost_label="value at risk left unhedged while the hedge waited on review",
)


async def run(offline: bool) -> dict:
    banner(f"{SCENARIO.title}: with institutional memory")
    print("Transcript of the messages the agents exchanged through RetiQo, as a listening agent received them.")
    with_memory = await run_loop(SCENARIO, EXAMPLE_DIR, offline, use_memory=True, conversation=True)
    banner(f"{SCENARIO.title}: replayed without institutional memory (control)")
    print("(same cases; the proposer ignores the shared record)")
    without = await run_loop(SCENARIO, EXAMPLE_DIR, offline, use_memory=False, verbose=False)
    return {**compare(SCENARIO, with_memory, without), "per_round": with_memory}


if __name__ == "__main__":
    args = parse_args(__doc__.strip().splitlines()[0])
    asyncio.run(run(args.offline))
