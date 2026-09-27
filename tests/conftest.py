# Copyright 2026 Loreum Digital Inc
# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))
