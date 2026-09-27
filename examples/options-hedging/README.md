<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Options hedging: ten weekly hedge decisions and the desk knowledge between them

A trading agent protects a long equity position each week by buying put options. Compliance, Risk, Volatility and Execution agents enforce the desk's rules. What they catch becomes shared knowledge in RetiQo: how to size a hedge, what to do ahead of earnings, which names have unusable weekly options, which names are restricted and what to hedge them with, and at what beta. Before week five the trading agent is replaced by a new model; it inherits the desk's knowledge from the shared record.

> Illustrative only. Tickers and companies are fictional, and the option model is deliberately simple (fixed deltas and premiums for a one-month 97% put and a 97/87 put spread). This demonstrates the learning loop; it is not trading advice.

## Rules, and the lessons they leave behind

| Reviewer | Rule it enforces | Example lesson recorded in RetiQo |
|---|---|---|
| `risk-agent` | The hedge must offset 45-55% of the position's delta | Size hedges by option delta, not by notional: contracts = target delta / (100 x option delta) |
| `volatility-agent` | Don't pay inflated implied volatility ahead of a scheduled event | Before a scheduled event with IV rank 80+, use a 97/87 put spread: the short put offsets the inflated volatility |
| `execution-agent` | Don't trade options whose bid-ask spread eats the hedge | Use monthly expiries on HLVS; its weeklies trade 9% wide |
| `compliance-agent` | No trading in names on the restricted list | While HLVS is restricted, hedge it with SMIX options instead |
| `risk-agent` | Proxy hedges must be sized by beta | Size SMIX hedges for HLVS at beta 1.3 |

A lesson records the check and the facts it needs and which decision taught it. Before each new hedge, the trading agent applies every lesson that covers the new week.

Lessons chain. In week 5 the firm starts advising on a transaction involving Halvard Semiconductor, so HLVS goes on the restricted list. Compliance blocks the hedge; the agent switches to the sector index fund; Risk then points out that the proxy needs sizing at HLVS's beta of 1.3. Two lessons in one week, and in week 7, when HLVS is still restricted, the hedge goes through first time. In week 9, with the restriction lifted and earnings coming, the agent combines three lessons from three different reviewers (delta sizing, a put spread for event volatility, monthly expiries for HLVS) without a single objection.

## The conversation

With memory on, the agents also talk to each other. Every message is an `AgentMessage` interaction sent through RetiQo, like the records themselves, so the exchange is attributable and observable; a listening agent (`desk-log`) prints what it receives. `python main.py --offline` prints the full ten weeks. Two moments:

**Week 5: the hand-over, then a new restriction.** The replacement agent announces what it inherited, applies two lessons its predecessor learned, and then learns two new ones as Compliance and Risk object in turn.

```
--- trading-agent is replaced by trading-agent-v2 (new model, no local context) ---
trading-agent -> desk  [HANDOVER]
    Handing over to trading-agent-v2. Everything I learned is in the shared record.
trading-agent-v2 -> desk  [HELLO]
    Taking over from trading-agent. I have no memory of my own; from the shared record I loaded 3 lesson(s) and 4 past decision(s).

======== Decision 5 | Week 5 | Hedge 100,000 HLVS (Halvard Semiconductor) ========
trading-agent-v2 -> desk  [RECALL]
    Checked the shared record: 3 lesson(s) on file; 2 apply here:
    - Size hedges by option delta, not by notional: contracts = target delta / (100 x option delta) (learned in HEDGE-W01, by trading-agent)
    - Use monthly expiries on HLVS; its weeklies trade 9% wide (learned in HEDGE-W03, by trading-agent)
    On file but not relevant to this case:
    - Before a scheduled event with IV rank 80+, use a 97/87 put spread: the short put offsets the inflated volatility
trading-agent-v2 -> desk  [PROPOSAL]
    Proposal v1: Buy 1,250 HLVS monthly 97% put (premium $200,000)
compliance-agent -> trading-agent-v2  [OBJECTION]
    [restricted-list] HLVS is on the restricted list (the firm is advising on a transaction); no trading in its securities or options
risk-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: proxy-beta, delta-sizing.
volatility-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: event-volatility.
execution-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: option-liquidity.
trading-agent-v2 -> compliance-agent  [LEARNED]
    Understood. Fixing it and recording the lesson for next time: While HLVS is restricted, hedge it with SMIX options instead
trading-agent-v2 -> desk  [PROPOSAL]
    Proposal v2: Buy 400 SMIX monthly 97% put (premium $200,000)
compliance-agent -> trading-agent-v2  [RESOLVED]
    [restricted-list] fixed in v2. Objection withdrawn.
compliance-agent -> trading-agent-v2  [APPROVED]
    v2 approved. Checked: restricted-list.
risk-agent -> trading-agent-v2  [OBJECTION]
    [proxy-beta] SMIX hedge for HLVS ignores beta 1.3; it covers 38% of the risk
volatility-agent -> trading-agent-v2  [APPROVED]
    v2 approved. Checked: event-volatility.
execution-agent -> trading-agent-v2  [APPROVED]
    v2 approved. Checked: option-liquidity.
trading-agent-v2 -> risk-agent  [LEARNED]
    Understood. Fixing it and recording the lesson for next time: Size SMIX hedges for HLVS at beta 1.3
trading-agent-v2 -> desk  [PROPOSAL]
    Proposal v3: Buy 520 SMIX monthly 97% put (premium $260,000)
compliance-agent -> trading-agent-v2  [APPROVED]
    v3 approved. Checked: restricted-list.
risk-agent -> trading-agent-v2  [RESOLVED]
    [proxy-beta] fixed in v3. Objection withdrawn.
risk-agent -> trading-agent-v2  [APPROVED]
    v3 approved. Checked: proxy-beta, delta-sizing.
volatility-agent -> trading-agent-v2  [APPROVED]
    v3 approved. Checked: event-volatility.
execution-agent -> trading-agent-v2  [APPROVED]
    v3 approved. Checked: option-liquidity.
trading-agent-v2 -> desk  [DONE]
    All reviewers approved v3 after 2 revision(s). HedgeOrder HO-W05 written, linked to HEDGE-W05.
```

**Week 9: everything it needs is already known.** The agent cites where each lesson came from, and sets aside the ones that don't apply (HLVS is no longer restricted). No objections.

```
======== Decision 9 | Week 9 | Hedge 100,000 HLVS (Halvard Semiconductor), earnings in 6 days ========
trading-agent-v2 -> desk  [RECALL]
    Checked the shared record: 6 lesson(s) on file; 3 apply here:
    - Size hedges by option delta, not by notional: contracts = target delta / (100 x option delta) (learned in HEDGE-W01, by trading-agent)
    - Before a scheduled event with IV rank 80+, use a 97/87 put spread: the short put offsets the inflated volatility (learned in HEDGE-W02, by trading-agent)
    - Use monthly expiries on HLVS; its weeklies trade 9% wide (learned in HEDGE-W03, by trading-agent)
    On file but not relevant to this case:
    - While HLVS is restricted, hedge it with SMIX options instead
    - Size SMIX hedges for HLVS at beta 1.3
    - Use monthly expiries on KSTL; its weeklies trade 12% wide
trading-agent-v2 -> desk  [PROPOSAL]
    Proposal v1: Buy 1,786 HLVS monthly 97/87 put spread (premium $142,880)
compliance-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: restricted-list.
risk-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: proxy-beta, delta-sizing.
volatility-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: event-volatility.
execution-agent -> trading-agent-v2  [APPROVED]
    v1 approved. Checked: option-liquidity.
trading-agent-v2 -> desk  [DONE]
    All reviewers approved v1 first time. HedgeOrder HO-W09 written, linked to HEDGE-W09.
```

## What compounding looks like

```
    #  period     lessons known applied objections revisions  days   | without memory: objections  days
-------------------------------------------------------------------------------------------------------
    1  Week 1                 0       0          1         1     2   |                          1     2
    2  Week 2                 1       1          1         1     2   |                          2     2
    3  Week 3                 2       1          1         1     2   |                          2     2
    4  Week 4                 3       1          0         0     1   |                          1     2
    5  Week 5                 3       2          2         2     3   |                          4     3  <- new agent
    6  Week 6                 5       2          0         0     1   |                          2     2
    7  Week 7                 5       3          0         0     1   |                          4     3
    8  Week 8                 5       2          1         1     2   |                          3     2
    9  Week 9                 6       3          0         0     1   |                          3     2
   10  Week 10                6       2          0         0     1   |                          2     2
-------------------------------------------------------------------------------------------------------
total                         6                  6         6    16   |                         24    22

Approved first time: 5/10 with memory, 0/10 without
Days spent in review: 16 with memory, 22 without
Value at risk left unhedged while the hedge waited on review: $900,000 with memory, $1,867,000 without
```

**How to read the table.** *Lessons known* is how many lessons were on record when the hedge was proposed; *applied* is how many of them changed the plan before any reviewer saw it. On the right is the same week replayed without institutional memory: the trading agent ignores the record, so reviewers raise the same objections again and again. The dollar figure is the value at risk (a 2% daily move) on the position for each day it waited unhedged while the hedge was in review.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/options-hedging
python main.py --offline   # in-process simulation, no RetiQo host needed
python main.py             # against a RetiQo host: see the top-level README
```

Running against a host requires agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the weeks, the rules, the option model, and the replay without memory
- `schema.scd`: the State Channel Definition (a `HedgeOrder` class plus the shared memory classes)

Each approved hedge writes a `HedgeOrder` carrying the `decisionId` that authorized it. The loop itself lives in [`examples/common/loop.py`](../common/loop.py).
