<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Supply chain: eight shipment exceptions, one growing playbook

When a shipment is delayed, a logistics agent proposes a recovery plan, usually air-freighting the pallets the customer needs first. Five reviewing agents enforce their rules. Each objection becomes a lesson in RetiQo, so the playbook for the next exception is already in place, and the customer's line waits less time on internal review. Before the fifth exception the logistics agent is replaced; the replacement inherits the playbook.

## Rules, and the lessons they leave behind

| Reviewer | Rule it enforces | Example lesson recorded in RetiQo |
|---|---|---|
| `quality-agent` | Temperature-sensitive lots fly only with a cold-chain qualified carrier | Temperature-sensitive lots fly only with a cold-chain qualified carrier (Coldline Air) |
| `safety-agent` | Lithium batteries must fly cargo-only | Anything containing lithium batteries must fly cargo-only |
| `trade-compliance-agent` | Some lanes need documents before the border | Lane MTY-DAL needs Carta Porte and USMCA certificate of origin prepared up front |
| `finance-agent` | Expedites above $15,000 need a penalty-avoidance case | Attach the penalty-avoidance calculation to any expedite above $15,000 |
| `customer-service-agent` | Key accounts hear about delays from us first | Halden Manufacturing is a key account: notify them with a new ETA as part of the plan |

A lesson records the check and the facts it needs (a supplier, a lane, a threshold, a verified account) and which decision taught it. Before each new proposal, the proposing agent applies every lesson that covers the new case.

Lessons are specific where the world is specific (a lane's documents, a key account) and general where the rule is general (lithium, cold chain, cost justification). A new key account (Vantor Medical) still costs one objection; everything already learned is applied to it automatically.

## What compounding looks like

```
    #  period     lessons known applied objections revisions  days   | without memory: objections  days
-------------------------------------------------------------------------------------------------------
    1  Jan 12                 0       0          3         1     2   |                          3     2
    2  Jan 29                 3       2          1         1     2   |                          3     2
    3  Feb 10                 4       1          1         1     2   |                          2     2
    4  Feb 24                 5       3          0         0     1   |                          3     3
    5  Mar 9                  5       2          0         0     1   |                          2     2  <- new agent
    6  Mar 23                 5       2          1         1     2   |                          3     2
    7  Apr 6                  6       3          0         0     1   |                          3     2
    8  Apr 20                 6       2          0         0     1   |                          3     2
-------------------------------------------------------------------------------------------------------
total                         6                  6         4    12   |                         22    17

Approved first time: 4/8 with memory, 0/8 without
Days spent in review: 12 with memory, 17 without
Customer line-stoppage penalties while the plan waited on review: $54,000 with memory, $123,000 without
```

**How to read the table.** *Lessons known* is how many lessons were on record when the decision was proposed; *applied* is how many of them changed the plan before any reviewer saw it. On the right is the same decision replayed without institutional memory: the proposer ignores the record, so reviewers raise the same objections again and again. The numbers are from the offline run; they depend only on the scenario, so a run against a host should give the same table.

The dollar figure is the customer's line-stoppage penalty for the days the plan spent waiting on internal review.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/supply-chain-coordination
python main.py --offline   # in-process simulation, no RetiQo host needed
python main.py             # against a RetiQo host: see the top-level README
```

Running against a host requires agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the cases, the rules, and the replay without memory
- `schema.scd`: the State Channel Definition (domain classes plus the shared memory classes)

Each approved plan writes a `Shipment` booking carrying the `decisionId` that authorized it. The loop itself lives in [`examples/common/loop.py`](../common/loop.py).
