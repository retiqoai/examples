<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Enterprise multi-agent: eight quarters of inventory reorders

A procurement agent proposes a quarterly reorder of an industrial sensor. Four reviewing agents each enforce their department's rules. Every objection becomes a lesson in RetiQo, and every later reorder is sized with all the lessons that apply before anyone reviews it. Before quarter five the procurement agent is replaced by a new model; it inherits what its predecessor learned from the shared record.

## Rules, and the lessons they leave behind

| Reviewer | Rule it enforces | Example lesson recorded in RetiQo |
|---|---|---|
| `inventory-agent` | Stock already on open purchase orders must be subtracted | Subtract units already inbound on open POs before sizing a reorder |
| `quality-agent` | No orders from a supplier on quality hold | When Northgate Components is on quality hold, order from Corvale Parts |
| `vendor-agent` | Respect each supplier's minimum order quantity | Brandt Electronics has a minimum order of 100 units |
| `finance-agent` | Year-end spending freeze caps new orders at $5,000 | During the year-end freeze (Q4-Q1), split orders to stay under $5,000 |
| `finance-agent` | Orders above $15,000 need two competing quotes | Attach two competing quotes to any order above $15,000 |

A lesson records the check and the facts it needs (a supplier, a lane, a threshold, a verified account) and which decision taught it. Before each new proposal, the proposing agent applies every lesson that covers the new case.

Problems show up over time the way they do in a real business: stock already inbound (Q1), a supplier quality hold (Q2), the year-end freeze (Q4), a demand spike that crosses the quote threshold (Q2 2027), a small top-up below a new supplier's minimum (Q3 2027). Some come back: the freeze returns every year-end, and Northgate goes on hold again in Q4 2027. With memory, each problem costs a review cycle once. Without it, every quarter pays again.

## What compounding looks like

```
    #  period     lessons known applied objections revisions  days   | without memory: objections  days
-------------------------------------------------------------------------------------------------------
    1  Q1 2026                0       0          1         1     6   |                          1     6
    2  Q2 2026                1       0          1         1     6   |                          1     6
    3  Q3 2026                2       2          0         0     3   |                          2     6
    4  Q4 2026                2       2          1         1     6   |                          3     6
    5  Q1 2027                3       1          0         0     3   |                          1     6  <- new agent
    6  Q2 2027                3       1          1         1     6   |                          2     6
    7  Q3 2027                4       1          1         1     6   |                          2     9
    8  Q4 2027                5       3          0         0     3   |                          3     6
-------------------------------------------------------------------------------------------------------
total                         5                  5         5    39   |                         15    51

Approved first time: 3/8 with memory, 0/8 without
Days spent in review: 39 with memory, 51 without
Stockout exposure while waiting for approval: $24,000 with memory, $40,500 without
```

**How to read the table.** *Lessons known* is how many lessons were on record when the decision was proposed; *applied* is how many of them changed the plan before any reviewer saw it. On the right is the same decision replayed without institutional memory: the proposer ignores the record, so reviewers raise the same objections again and again. The numbers are from the offline run; they depend only on the scenario, so a run against a host should give the same table.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/enterprise-multi-agent
python main.py --offline   # in-process simulation, no RetiQo host needed
python main.py             # against a RetiQo host: see the top-level README
```

Running against a host requires agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the cases, the rules, and the replay without memory
- `schema.scd`: the State Channel Definition (domain classes plus the shared memory classes)

Each approved reorder writes a `PurchaseOrder` carrying the `decisionId` that authorized it. The loop itself lives in [`examples/common/loop.py`](../common/loop.py).
