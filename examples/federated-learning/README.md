<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Federated learning: eight release decisions across hospitals

Three hospitals train a chest X-ray model together without sharing patient data. After each training round a coordinator agent proposes releasing the aggregated model; clinical validation, privacy and clinical governance agents enforce the release rules. Only metrics and decisions are written to RetiQo. Before round 15 the coordinator is replaced by a new agent, which inherits the release playbook.

## Rules, and the lessons they leave behind

| Reviewer | Rule it enforces | Example lesson recorded in RetiQo |
|---|---|---|
| `clinical-validation-agent` | Sites whose scanner shifts the model need a calibration layer | Any site imaging with the Vireo X9 needs its local calibration layer in the release |
| `clinical-validation-agent` | Keep the AUC gap between age groups under 0.05 | Reweight by age group before release; keep the subgroup AUC gap under 0.05 |
| `privacy-officer-agent` | Stay within the lifetime differential-privacy budget | Near the lifetime budget of 4.0, train with the higher noise multiplier (epsilon 0.02 per round) |
| `clinical-governance-agent` | Production release needs validation at all three sites | If fewer than 3 sites validate, release in shadow mode instead |

A lesson records the check and the facts it needs (a supplier, a lane, a threshold, a verified account) and which decision taught it. Before each new proposal, the proposing agent applies every lesson that covers the new case.

Lessons generalize. The calibration learned for site B's new Vireo X9 scanner in round 12 is applied automatically in round 16, when site C installs the same scanner: no objection, no lost week.

## What compounding looks like

```
    #  period     lessons known applied objections revisions  days   | without memory: objections  days
-------------------------------------------------------------------------------------------------------
    1  Round 12               0       0          1         1    10   |                          1    10
    2  Round 13               1       1          1         1    10   |                          2    10
    3  Round 14               2       2          0         0     5   |                          2    10
    4  Round 15               2       2          1         1    10   |                          2    10  <- new agent
    5  Round 16               3       3          0         0     5   |                          2    10
    6  Round 17               3       3          1         1    10   |                          3    10
    7  Round 18               4       3          0         0     5   |                          3    10
    8  Round 19               4       4          0         0     5   |                          3    10
-------------------------------------------------------------------------------------------------------
total                         4                  4         4    60   |                         18    80

Approved first time: 4/8 with memory, 0/8 without
Days spent in review: 60 with memory, 80 without
```

**How to read the table.** *Lessons known* is how many lessons were on record when the decision was proposed; *applied* is how many of them changed the plan before any reviewer saw it. On the right is the same decision replayed without institutional memory: the proposer ignores the record, so reviewers raise the same objections again and again. The numbers are from the offline run; they depend only on the scenario, so a run against a host should give the same table.

No patient data is written to RetiQo: records hold metrics, decisions and reasons only.

## Run it

```bash
pipenv shell               # once, from the repository root
cd examples/federated-learning
python main.py --offline   # in-process simulation, no RetiQo host needed
python main.py             # against a RetiQo host: see the top-level README
```

Running against a host requires agents provisioned in advance in the RetiQo portal (status Pending, in your application). The top-level README walks through it.

## Files

- `main.py`: the cases, the rules, and the replay without memory
- `schema.scd`: the State Channel Definition (domain classes plus the shared memory classes)

Each approved release writes a `ModelRelease` (production or shadow) carrying the `decisionId` that authorized it. The loop itself lives in [`examples/common/loop.py`](../common/loop.py).
