# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Federated learning: eight release decisions for a model trained across hospitals.

Three hospitals train a chest X-ray model together without sharing patient data. After each
training round a coordinator agent proposes releasing the aggregated model. Clinical
Validation, Privacy and Clinical Governance agents enforce the rules: a per-site calibration
layer for scanners that shift the model's accuracy, a cap on the accuracy gap between patient
subgroups, a lifetime differential-privacy budget, and shadow mode when fewer than three
sites could validate. Only metrics and decisions are written to RetiQo; no patient data.

Every objection becomes a lesson in RetiQo. Lessons generalize: the calibration learned for
one hospital's new scanner is applied automatically when another hospital installs the same
model. Before round 15 the coordinator agent is replaced; the replacement picks up the
release playbook from the shared record. The eight rounds are then replayed without memory.

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

PRIVACY_BUDGET = 4.0          # lifetime epsilon agreed by the three hospitals
DEFAULT_EPSILON = 0.3         # privacy cost of a round at the default noise level
LOW_EPSILON = 0.02            # with the higher noise multiplier
MAX_SUBGROUP_GAP = 0.05       # largest allowed AUC gap between age groups
SHIFTING_SCANNERS = {"Vireo X9"}  # scanners whose images shift the model without calibration

OLD = "Lumen 400"
NEW = "Vireo X9"

# `gap` is the subgroup AUC gap before reweighting; `spent` is epsilon used so far.
CASES = [
    dict(id="R12", period="Round 12", scanners={"site-a": OLD, "site-b": NEW, "site-c": OLD},
         spent=2.9, gap=0.03, sites_reporting=3, observed="Site B AUC 0.90 with calibration"),
    dict(id="R13", period="Round 13", scanners={"site-a": OLD, "site-b": NEW, "site-c": OLD},
         spent=3.2, gap=0.07, sites_reporting=3, observed="Subgroup gap 0.02 after reweighting"),
    dict(id="R14", period="Round 14", scanners={"site-a": OLD, "site-b": NEW, "site-c": OLD},
         spent=3.5, gap=0.06, sites_reporting=3, observed="All sites within 0.01 of validation AUC"),
    dict(id="R15", period="Round 15", scanners={"site-a": OLD, "site-b": NEW, "site-c": OLD},
         spent=3.8, gap=0.04, sites_reporting=3, observed="Released at epsilon 0.02; AUC unchanged"),
    dict(id="R16", period="Round 16", scanners={"site-a": OLD, "site-b": NEW, "site-c": NEW},
         spent=3.82, gap=0.03, sites_reporting=3, observed="Site C's new scanner calibrated on day one"),
    dict(id="R17", period="Round 17", scanners={"site-a": OLD, "site-b": NEW, "site-c": NEW},
         spent=3.84, gap=0.04, sites_reporting=2, observed="Shadow mode until site A validated a week later"),
    dict(id="R18", period="Round 18", scanners={"site-a": OLD, "site-b": NEW, "site-c": NEW},
         spent=3.86, gap=0.06, sites_reporting=3, observed="Released; production AUC 0.92 across sites"),
    dict(id="R19", period="Round 19", scanners={"site-a": OLD, "site-b": NEW, "site-c": NEW},
         spent=3.88, gap=0.03, sites_reporting=2, observed="Shadow mode during site A's maintenance window"),
]


def base_terms(case):
    return {"model": f"ChestXR-{case['id']}", "calibrated_sites": [], "epsilon": DEFAULT_EPSILON,
            "reweighted": False, "mode": "production"}


def describe(t):
    text = f"Release {t['model']} in {t['mode']} mode at epsilon {t['epsilon']}"
    if t["calibrated_sites"]:
        text += f", with calibration for {', '.join(t['calibrated_sites'])}"
    if t["reweighted"]:
        text += ", subgroup-reweighted"
    return text


def uncalibrated(case, terms):
    return [s for s, scanner in sorted(case["scanners"].items())
            if scanner in SHIFTING_SCANNERS and s not in terms["calibrated_sites"]]


def gap(case, terms):
    return round(case["gap"] * (0.4 if terms["reweighted"] else 1.0), 3)


RULES = [
    Rule(
        check="scanner-calibration", role="clinical-validation",
        violated=lambda c, t: (f"{', '.join(uncalibrated(c, t))} uses the {NEW} scanner; "
                               "local AUC drops from 0.91 to 0.84 without a calibration layer")
        if uncalibrated(c, t) else None,
        learn=lambda c, t: {"scanner": NEW},
        covers=lambda c, f: f["scanner"] in c["scanners"].values(),
        fix=lambda c, t, f: {**t, "calibrated_sites": sorted(set(t["calibrated_sites"]) | {
            s for s, scanner in c["scanners"].items() if scanner == f["scanner"]})},
        summary=lambda f: f"Any site imaging with the {f['scanner']} needs its local calibration layer in the release",
    ),
    Rule(
        check="subgroup-gap", role="clinical-validation",
        violated=lambda c, t: f"AUC gap between age groups is {gap(c, t):.2f}; the limit is {MAX_SUBGROUP_GAP:.2f}"
        if gap(c, t) > MAX_SUBGROUP_GAP else None,
        learn=lambda c, t: {"limit": MAX_SUBGROUP_GAP},
        covers=lambda c, f: True,
        fix=lambda c, t, f: {**t, "reweighted": True},
        summary=lambda f: f"Reweight by age group before release; keep the subgroup AUC gap under {f['limit']:.2f}",
    ),
    Rule(
        check="privacy-budget", role="privacy",
        violated=lambda c, t: (f"Epsilon {c['spent']:.2f} spent + {t['epsilon']} this round exceeds the "
                               f"lifetime budget of {PRIVACY_BUDGET}")
        if c["spent"] + t["epsilon"] > PRIVACY_BUDGET + 1e-9 else None,
        learn=lambda c, t: {"budget": PRIVACY_BUDGET, "epsilon": LOW_EPSILON},
        covers=lambda c, f: c["spent"] + DEFAULT_EPSILON > f["budget"],
        fix=lambda c, t, f: {**t, "epsilon": f["epsilon"]},
        summary=lambda f: (f"Near the lifetime budget of {f['budget']}, train with the higher noise "
                           f"multiplier (epsilon {f['epsilon']} per round)"),
    ),
    Rule(
        check="minimum-sites", role="clinical-governance",
        violated=lambda c, t: f"Only {c['sites_reporting']} of 3 sites validated this round; production release needs all 3"
        if c["sites_reporting"] < 3 and t["mode"] == "production" else None,
        learn=lambda c, t: {"required_sites": 3},
        covers=lambda c, f: c["sites_reporting"] < f["required_sites"],
        fix=lambda c, t, f: {**t, "mode": "shadow"},
        summary=lambda f: f"If fewer than {f['required_sites']} sites validate, release in shadow mode instead",
    ),
]

SCENARIO = Scenario(
    title="Federated model releases, 8 rounds",
    workflow="model-release",
    decision_prefix="RELEASE",
    proposer=Participant("coordinator-agent", "CoordinatorAgent"),
    reviewers=[
        Participant("clinical-validation-agent", "ClinicalValidationAgent", "clinical-validation"),
        Participant("privacy-officer-agent", "PrivacyAgent", "privacy"),
        Participant("clinical-governance-agent", "ClinicalGovernanceAgent", "clinical-governance"),
    ],
    rules=RULES,
    cases=CASES,
    base_terms=base_terms,
    describe=describe,
    subject=lambda c: f"Release the ChestXR model after {c['period'].lower()}",
    outcome=lambda c, t: ("AUC at or above 0.90 at every site; subgroup gap under 0.05", c["observed"]),
    review_cycle_days=5,
    swap_before_round=4,
    domain_record=("ModelRelease", ["modelId", "decisionId", "round", "validationAuc", "status"],
                   lambda c, t, d: (t["model"], {
                       "modelId": t["model"], "decisionId": d, "round": c["id"][1:],
                       "validationAuc": "0.92", "status": t["mode"].upper()})),
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
