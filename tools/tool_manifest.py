#!/usr/bin/env python3
"""Print her tools as MCP-shaped definitions (logic/tool_manifest.py)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic.tool_manifest import manifest  # noqa: E402

if __name__ == "__main__":
    json.dump(manifest(), sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write("\n")
