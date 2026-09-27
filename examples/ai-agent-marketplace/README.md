<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# AI agent marketplace: eight sourcing decisions, compounding vendor knowledge

An analytics team keeps buying work from AI agents on a marketplace: churn models, demand forecasts, ticket triage, contract review. A sourcing agent proposes the bid with the best benchmark; five reviewing agents enforce vendor-risk rules. What they teach accumulates: which providers are disqualified and why, which deployments satisfy data residency, what each job type may cost, and how providers actually performed against their claims. Before the fifth job the sourcing agent is replaced.

## Rules, and the lessons they leave behind

| Reviewer | Rule it enforces | Example lesson recorded in RetiQo |
|---|---|---|
| `governance-agent` | EU customer records stay in the EU | Jobs using EU customer records must use an EU deployment |
| `security-agent` | Providers need a current SOC 2 Type II report | Solvane AI is disqualified until it has a SOC 2 Type II report |
| `analytics-lead-agent` | Don't select on a benchmark a provider failed to deliver | Quarry Data over-claims: delivered 0.71 vs 0.84 claimed; do not select on its benchmark |
| `procurement-agent` | Each job type has a price ceiling | Contract review jobs are capped at $3,000 |
| `legal-agent` | Providers may not train on company data | Contract Brightline Analytics only with the training opt-out addendum |

A lesson records the check and the facts it needs (a supplier, a lane, a threshold, a verified account) and which decision taught it. Before each new proposal, the proposing agent applies every lesson that covers the new case.

The highest-scoring bid is often the wrong choice for reasons only earlier jobs revealed. The delivered-quality lesson comes straight from a recorded Outcome: Quarry Data's first job under-delivered, so the next time it tops the benchmark table it is passed over.

## What compounding looks like

```
    #  period     lessons known applied objections revisions  days   | without memory: objections  days
-------------------------------------------------------------------------------------------------------
    1  Q1 2026                0       0          2         1     4   |                          2     4
    2  Q1 2026                2       0          0         0     2   |                          0     2
    3  Q2 2026                2       1          1         1     4   |                          3     6
    4  Q2 2026                3       0          1         1     4   |                          2     6
    5  Q3 2026                4       2          0         0     2   |                          2     4  <- new agent
    6  Q3 2026                4       2          1         1     4   |                          4     8
    7  Q4 2026                5       3          0         0     2   |                          3     6
    8  Q4 2026                5       2          0         0     2   |                          2     6
-------------------------------------------------------------------------------------------------------
total                         5                  5         4    24   |                         18    42

Approved first time: 4/8 with memory, 1/8 without
Days spent in review: 24 with memory, 42 without
```

**How to read the table.** *Lessons known* is how many lessons were on record when the decision was proposed; *applied* is how many of them changed the plan before any reviewer saw it. On the right is the same decision replayed without institutional memory: the proposer ignores the record, so reviewers raise the same objections again and again. The numbers are from the offline run; they depend only on the scenario, so a run against a host should give the same table.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/ai-agent-marketplace
python main.py --offline   # in-process simulation, no RetiQo host needed
python main.py             # against a RetiQo host: see the top-level README
```

Running against a host requires agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the cases, the rules, and the replay without memory
- `schema.scd`: the State Channel Definition (domain classes plus the shared memory classes)

Each approved choice writes a `ServiceAgreement` carrying the `decisionId` that authorized it. The loop itself lives in [`examples/common/loop.py`](../common/loop.py).
