<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Treasury approvals: ten payment runs and the controls knowledge between them

An accounts-payable agent proposes each supplier payment; Controls, Treasury and Vendor Compliance agents enforce the rules that protect the company. What they catch becomes shared knowledge: verified bank accounts, suppliers' discount terms, duplicate-invoice patterns, policy thresholds. Before run six the payables agent is replaced; the replacement inherits it all.

## Rules, and the lessons they leave behind

| Reviewer | Rule it enforces | Example lesson recorded in RetiQo |
|---|---|---|
| `controls-agent` | Catch invoices resubmitted with a different number format | Compare invoice numbers with dashes and spaces removed before paying |
| `controls-agent` | Changed bank details need call-back verification (TR-7) | Pinecrest Toys account ending 4471 was verified by call-back to the contact in the vendor master |
| `treasury-agent` | Take early-payment discounts | Harbor Freightways offers 2/10 net 30: pay on day 10 to take the discount |
| `treasury-agent` | Payments above $100,000 need a second approver | Route payments above $100,000 for dual approval up front |
| `compliance-agent` | No payment to a new vendor without a W-9 | Request the W-9 when a new vendor's first invoice arrives, before the payment run |

A lesson records the check and the facts it needs (a supplier, a lane, a threshold, a verified account) and which decision taught it. Before each new proposal, the proposing agent applies every lesson that covers the new case.

Memory doesn't make controls weaker. A verified account stays verified, but when Pinecrest changes banks a second time (run 9), the lesson no longer covers it and Controls blocks the payment again, exactly as it should.

## What compounding looks like

```
    #  period     lessons known applied objections revisions  days   | without memory: objections  days
-------------------------------------------------------------------------------------------------------
    1  Week 1                 0       0          1         1     2   |                          1     2
    2  Week 2                 1       0          1         1     2   |                          1     2
    3  Week 3                 2       1          0         0     1   |                          1     2
    4  Week 4                 2       1          0         0     1   |                          1     2
    5  Week 5                 2       0          1         1     2   |                          1     2
    6  Week 6                 3       1          1         1     2   |                          2     2  <- new agent
    7  Week 7                 4       1          1         1     2   |                          2     2
    8  Week 8                 5       1          0         0     1   |                          1     2
    9  Week 9                 5       0          1         1     2   |                          1     2
   10  Week 10                6       2          0         0     1   |                          2     2
-------------------------------------------------------------------------------------------------------
total                         6                  6         6    16   |                         13    20

Approved first time: 4/10 with memory, 0/10 without
Days spent in review: 16 with memory, 20 without
```

**How to read the table.** *Lessons known* is how many lessons were on record when the decision was proposed; *applied* is how many of them changed the plan before any reviewer saw it. On the right is the same decision replayed without institutional memory: the proposer ignores the record, so reviewers raise the same objections again and again. The numbers are from the offline run; they depend only on the scenario, so a run against a host should give the same table.

All names, invoices and account fragments are fictional; only the last four digits of an account ever appear.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/treasury-approvals
python main.py --offline   # in-process simulation, no RetiQo host needed
python main.py             # against a RetiQo host: see the top-level README
```

Running against a host requires agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the cases, the rules, and the replay without memory
- `schema.scd`: the State Channel Definition (domain classes plus the shared memory classes)

Each decision writes a `PaymentRelease` (released or held) carrying the `decisionId` that authorized it. The loop itself lives in [`examples/common/loop.py`](../common/loop.py).
