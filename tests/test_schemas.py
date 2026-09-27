# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""Every example's State Channel Definition is valid and carries the shared memory model."""
import json
from pathlib import Path

import pytest

from common.ledger import MEMORY_CLASSES, MEMORY_INTERACTIONS

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SCHEMAS = sorted(EXAMPLES.glob("*/schema.scd"))


def test_every_example_has_a_schema():
    examples = {p.name for p in EXAMPLES.iterdir() if (p / "main.py").exists()}
    assert examples == {p.parent.name for p in SCHEMAS}


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=lambda p: p.parent.name)
def test_schema_declares_memory_model(schema_path):
    scd = json.loads(schema_path.read_text())
    object_root = next(e for e in scd["entities"] if e["name"] == "ObjectRoot")
    classes = {e["name"]: [a["name"] for a in e.get("attributes", [])] for e in object_root["entities"]}
    for name, attributes in MEMORY_CLASSES.items():
        assert classes.get(name) == attributes, f"{name} out of date; run tools/sync_memory_schema.py"

    interaction_root = next(i for i in scd["interactions"] if i["name"] == "InteractionRoot")
    interactions = {i["name"]: i.get("parameters", []) for i in interaction_root["interactions"]}
    for name, parameters in MEMORY_INTERACTIONS.items():
        assert interactions.get(name) == parameters, f"{name} out of date; run tools/sync_memory_schema.py"
