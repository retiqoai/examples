# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
"""
Keep the institutional-memory classes identical in every example's schema.scd.

The memory model (Decision, Review, Objection, Outcome and their notifications) is defined
once in examples/common/ledger.py. Run this after changing it:

    python tools/sync_memory_schema.py

Domain classes in each schema are left untouched.
"""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load ledger.py on its own so this tool runs without the RetiQo SDK installed.
_spec = importlib.util.spec_from_file_location("ledger", ROOT / "examples" / "common" / "ledger.py")
_ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ledger)
MEMORY_CLASSES = _ledger.MEMORY_CLASSES
MEMORY_INTERACTIONS = _ledger.MEMORY_INTERACTIONS



def sync(schema_path: Path) -> bool:
    scd = json.loads(schema_path.read_text())
    object_root = next(e for e in scd["entities"] if e["name"] == "ObjectRoot")
    interaction_root = next(i for i in scd["interactions"] if i["name"] == "InteractionRoot")

    domain_entities = [e for e in object_root["entities"] if e["name"] not in MEMORY_CLASSES]
    object_root["entities"] = domain_entities + [
        {"name": name, "attributes": [{"name": a} for a in attributes]}
        for name, attributes in MEMORY_CLASSES.items()
    ]
    domain_interactions = [
        i for i in interaction_root["interactions"] if i["name"] not in MEMORY_INTERACTIONS
    ]
    interaction_root["interactions"] = domain_interactions + [
        {"name": name, "parameters": list(parameters)}
        for name, parameters in MEMORY_INTERACTIONS.items()
    ]

    text = json.dumps(scd, indent="\t") + "\n"
    # Keep one-field objects such as {"name": "status"} on a single line.
    text = re.sub(r'\{\n\t+("name": "[^"]*")\n\t+\}', r'{\1}', text)
    changed = text != schema_path.read_text()
    schema_path.write_text(text)
    return changed


def main() -> None:
    for schema in sorted((ROOT / "examples").glob("*/schema.scd")):
        print(f"{'updated' if sync(schema) else 'unchanged'}: {schema.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
