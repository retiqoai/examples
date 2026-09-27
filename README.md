<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# RetiQo Examples

**Models think. State remembers.**

These examples show RetiQo as institutional memory for AI agents, and the learning loop it makes possible.

In each example, a proposing agent works through a series of real decisions (quarterly reorders, shipment exceptions, vendor selections, model releases, payment runs, option hedges) while reviewing agents enforce their departments' rules. Every objection becomes a **lesson** in RetiQo: the check to run next time and the facts it needs. Every later decision starts from all the lessons that apply. Knowledge compounds: a problem costs a review cycle once, then stops recurring. Partway through, the proposing agent is replaced by a new one; it catches up from the shared record, and the improvement does not reset.

Each example then replays the same decisions **without** institutional memory, as a control.

## Results

From the offline runs. The scenarios are illustrative: the cases and rules are scripted to reflect common practice in each domain, so these figures show the mechanism at work, not a measured benchmark from a deployment. They depend only on the scenarios, so a run against a RetiQo host should produce the same numbers.

| Example | Decisions | Objections with memory | without | First-time approvals with memory | without | Days in review with memory | without |
|---|---|---|---|---|---|---|---|
| [Inventory reorders](examples/enterprise-multi-agent/) | 8 | 5 | 15 | 3 | 0 | 39 | 51 |
| [Shipment exceptions](examples/supply-chain-coordination/) | 8 | 6 | 22 | 4 | 0 | 12 | 17 |
| [AI service sourcing](examples/ai-agent-marketplace/) | 8 | 5 | 18 | 4 | 1 | 24 | 42 |
| [Model releases](examples/federated-learning/) | 8 | 4 | 18 | 4 | 0 | 60 | 80 |
| [Supplier payments](examples/treasury-approvals/) | 10 | 6 | 13 | 4 | 0 | 16 | 20 |
| [Options hedging](examples/options-hedging/) | 10 | 6 | 24 | 5 | 0 | 16 | 22 |

## Examples

| Example | The recurring decision | Knowledge that accumulates |
|---|---|---|
| [enterprise-multi-agent](examples/enterprise-multi-agent/) | Quarterly inventory reorders | Inbound stock, supplier quality holds, minimum order quantities, the year-end freeze, quote thresholds |
| [supply-chain-coordination](examples/supply-chain-coordination/) | Recovering delayed shipments | Cold-chain carriers, lithium shipping rules, lane documents, key-account notice, expedite justification |
| [ai-agent-marketplace](examples/ai-agent-marketplace/) | Sourcing AI analysis jobs | Data residency, disqualified providers, delivered-vs-claimed quality, price ceilings, contract terms |
| [federated-learning](examples/federated-learning/) | Releasing a model trained across hospitals | Scanner calibration, subgroup fairness, the privacy budget, shadow-mode releases |
| [treasury-approvals](examples/treasury-approvals/) | Weekly supplier payment runs | Verified bank changes, duplicate invoices, discount terms, dual approval, new-vendor W-9s |
| [options-hedging](examples/options-hedging/) | Weekly option hedges on a trading desk | Delta sizing, event-volatility structures, illiquid expiries, restricted names and their proxies, proxy betas |
| [performance-test](examples/performance-test/) | (benchmark) | How fast decision records reach other agents |

## The shared memory model

Every example uses the same record types, defined once in [`examples/common/ledger.py`](examples/common/ledger.py) and declared in each `schema.scd`:

| Record | Written by | Holds |
|---|---|---|
| **Decision** | the proposing agent | subject, proposal, structured terms, rationale, status, version, and the lessons applied up front |
| **Review** | each reviewer | role, verdict (`APPROVE`, `CONCERN` or `REJECT`), note, and the version reviewed |
| **Objection** | whoever objects | the check that failed, the reason, whether it blocks, and how it was resolved |
| **Outcome** | whoever observes the result | expected vs observed, variance, and what was learned |
| **Lesson** | whoever learned it | the check, the facts it needs (as JSON), a one-line summary, and the decision that taught it |

Agents can also message each other about a decision (`AgentMessage` interactions); the [options-hedging](examples/options-hedging/) example prints that conversation as a transcript.

Each record is a RetiQo object owned by the agent that wrote it: only the proposer changes its decision, only a reviewer changes its review. Other agents see every record through subscriptions, and an agent that joins later asks the owners for current values, so it starts from the full record.

A decision is approved only when every required role has reviewed its **current** version and no blocking objection is open. Revising a decision creates a new version, so earlier sign-offs don't carry over.

Domain records (purchase orders, shipments, payments...) carry the `decisionId` that authorized them, so operational state always traces back to who decided and why.

## How the learning loop works

[`examples/common/loop.py`](examples/common/loop.py) runs every example:

1. **Propose.** Start from a naive plan, then apply every lesson on record that covers this case (in a fixed rule order, so fixes compose predictably).
2. **Review.** Each reviewer checks the current version against the rules it owns. It approves, or rejects and raises a blocking objection naming the failed check.
3. **Learn.** For each objection the proposer fixes the plan and records a Lesson: the check plus the facts that made it fail (a supplier's minimum order, a verified account, a lane's documents). The same lesson is never recorded twice.
4. **Revise** and go back to review, until approved.
5. **Record** the outcome and the domain record, and move on to the next case.

A scenario is just data: the cases, the rules (how to detect a violation, what to learn, when a lesson applies, how to fix the plan), and the reviewers. Adding a new scenario doesn't need new infrastructure.

## Getting started

Requires Python 3.8 or later and [Pipenv](https://pipenv.pypa.io/) (`pip install --user pipenv`). Dependencies are declared in the `Pipfile`.

```bash
git clone https://github.com/retiqoai/examples.git retiqo-examples
cd retiqo-examples
pipenv install --dev    # creates the virtualenv, installs the SDK and pytest
pipenv shell            # activates it; later commands in this repo assume you're inside

# Run any example offline
python examples/enterprise-multi-agent/main.py --offline

# Run the tests (offline, no host needed)
pytest
```

Without `pipenv shell`, prefix commands with `pipenv run` (for example `pipenv run test`). Pipenv also loads `.env` automatically.

### The RetiQo Python SDK

The examples are built on the [RetiQo Python SDK](https://github.com/retiqoai/retiqo_sdk) (package `retiqo`), a separate library. It is published on [PyPI](https://pypi.org/project/retiqo/), and `pipenv install` installs it for you. It is needed even for offline runs, because the agents use its actor interface.

To add the SDK to your own project:

```bash
pipenv install retiqo    # or: pip install retiqo
```

Check the installed version with `pipenv graph` or `pip show retiqo`. The SDK's [README](https://github.com/retiqoai/retiqo_sdk#readme) and [Quick Start](https://github.com/retiqoai/retiqo_sdk/blob/main/QUICK_START.md) cover its API. To try unreleased changes, install from source with `pipenv install git+https://github.com/retiqoai/retiqo_sdk.git#egg=retiqo`.

### Running against a RetiQo host

> **The host only accepts agents that were provisioned in advance.** Every agent must first be created in the portal, in your application, with status **Pending**, and the application must be deployed to the instance host you connect to. The examples never create agents on the fly: they use the agent IDs you list in `.retiqo/devices.txt`, and stop with an explanation if there aren't enough.

Offline runs need nothing else. To run the same examples on RetiQo infrastructure you need access to a RetiQo instance host and its portal: the portal's web address, and the host's WebSocket URL (for example `wss://host.example.com/ws`). Then, in the portal:

1. **Create an application.** *Applications → Create Application.* Give it a name (for example "RetiQo examples") and copy its ID.
2. **Deploy it to your instance host.** Open the application and add an *App Deployment* for the instance your host URL points to. Agents can't open a channel for an application that isn't deployed to that instance.
3. **Create the agents.** *Agents → New Agent*, once per agent, each with:
   - **Application:** the one from step 1
   - **Status:** Pending (RetiQo only activates agents in this state)
   - **Agent Type:** Generic

   Create **8**. The largest example uses 7 agents at once, and agents are reused across examples and runs. Copy each agent's ID.
4. **Optional: upload the schemas as contracts.** Open the application and add a contract per example, pasting that example's `schema.scd` as its State Channel Definition. An application holds up to 5 contracts, so this is optional: without a contract ID, the schema is sent when the execution is created.

Then, in the repository:

```bash
cp .env.example .env            # set RETIQO_HOST_URL and RETIQO_APP_ID
mkdir -p .retiqo
# one agent ID per line, from step 3
printf '%s\n' <agent-id-1> <agent-id-2> ... <agent-id-8> > .retiqo/devices.txt

python examples/options-hedging/main.py      # no --offline
```

The first time each agent is used, it is provisioned: it generates its own key pair and registers its address with the host, which moves it from Pending to Active. Its address and private key are saved to `.retiqo/credentials.json`, readable only by you, and reused on every later run. **Keep `.retiqo/` private.** It is git-ignored; never commit or share it. If you lose it, create new agents in the portal and replace the IDs in `devices.txt`.

If you uploaded contracts, add their IDs to `.env` per example, for example `RETIQO_CONTRACT_ID_OPTIONS_HEDGING=<contract-id>` (see `.env.example`).

## Repository layout

```
examples/
  common/                  shared code: memory model, actor, runtime, offline simulation
  <example>/main.py        the flow
  <example>/schema.scd     State Channel Definition
  <example>/README.md      what the example shows
tests/                     offline tests for the memory model, schemas and every example
tools/sync_memory_schema.py  keeps the memory classes identical in every schema.scd
```

## Offline mode

`--offline` replaces the RetiQo host with an in-process simulation (`examples/common/local.py`) that implements the parts of the API the examples use: publish/subscribe, object ownership, attribute updates and interactions. It is a teaching and testing aid. It has no persistence, signing, consensus or network, and its performance figures say nothing about a real host.

## Links

- [RetiQo Python SDK](https://github.com/retiqoai/retiqo_sdk)

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). All companies, tickers, people, invoices and figures in the examples are fictional, and nothing in them is financial or trading advice.
