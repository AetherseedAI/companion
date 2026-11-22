"""Her tools, described in the open shape the Model Context Protocol uses for
a tool: a name, a description, a JSON Schema for what it takes, and hints
about what it does.

Nothing here runs a tool, and nothing goes out: the unit speaks no protocol
to anyone. The shape is for what comes after this build - another model,
another host, another unit - which can read her tools as they are, without
this code. Asked for by the steward with the research of 29 Oct 2026 ("MCP
(tools) and Agent Skills ... sit in the Agentic AI Foundation under the
Linux Foundation").

The routes stay the build's: a message reaches a tool by the patterns of
intent_detection.py, never by the model choosing one. Each definition says
which capture of the pattern each argument is, the tier it needs and the
lowest trust level that has that tier (logic/levels.py), and whether the
unit says the result itself or the model words it.

    python3 tools/tool_manifest.py > tools.json
"""
import re

from intent_detection import INTENT_PATTERNS
from logic.levels import LADDER, PERMISSIONS

NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_FILE = {"type": "string", "description": "A file name in her workspace, e.g. plan.md",
         "maxLength": 200}
_ITEM = {"type": "string", "description": "The words of the item", "maxLength": 500}

# what each tool takes - in the order of the pattern's captures
ARGS = {
    "workspace_open": [],
    "file_list": [],
    "summarize": [("file", _FILE)],
    "file_read": [("file", _FILE)],
    "todo_add": [("item", _ITEM)],
    "todo_edit": [("which", {"type": "string", "description":
                             "The item's place (1 is the first) or words it holds",
                             "maxLength": 200}),
                  ("to", _ITEM)],
    "todo_remove": [("which", {"type": "string", "description":
                               "The item's place (1 is the first) or words it holds",
                               "maxLength": 200})],
    "todo_clear": [],
    "todo_read": [],
    "note_write": [("text", {"type": "string", "description": "What the note says",
                             "maxLength": 4000})],
    "note_list": [],
    "system_health": [],
    "trust_status": [],
    "file_search": [("query", {"type": "string", "description":
                               "A file name, or the words to search for", "maxLength": 200})],
    "calculate": [("expression", {"type": "string", "description":
                                  "Numbers and + - * / ** % ( ), or the words for them "
                                  "(times, divided by, plus, minus, squared)",
                                  "maxLength": 120})],
    "count_word": [("word", {"type": "string", "maxLength": 60}), ("file", _FILE)],
    "count": [("file", _FILE)],
    "compare": [("file_a", _FILE), ("file_b", _FILE)],
    "log_read": [],
    # her file tools (logic/file_tools.py): read from the message by parse()
    "file_save": [("file", _FILE), ("folder", {"type": "string", "maxLength": 200}),
                  ("format", {"type": "string", "maxLength": 20}),
                  ("when", {"type": "string", "enum": ["after", "last"]})],
    "file_append": [("file", _FILE), ("text", {"type": "string", "maxLength": 4000})],
    "file_write": [("file", _FILE), ("text", {"type": "string", "maxLength": 4000})],
    "folder_make": [("folder", {"type": "string", "maxLength": 200})],
    "file_move": [("from", _FILE), ("to", {"type": "string", "maxLength": 200})],
    "file_delete": [("file", _FILE)],
    "forget": [("what", {"type": "string", "description":
                         "What she is to forget, as the steward said it", "maxLength": 500})],
}

DESTRUCTIVE = frozenset({"todo_edit", "todo_remove", "todo_clear", "forget",
                         "file_move", "file_delete"})
# the result said by the unit word for word, model not called (proxy.py)
SAID_BY_THE_UNIT = frozenset({"workspace_open", "todo_add", "todo_edit", "todo_remove",
                              "todo_clear", "todo_read", "note_write", "note_list",
                              "file_list", "file_search", "calculate", "count", "count_word",
                              "compare", "forget",
                              "file_save", "file_append", "file_write", "folder_make",
                              "file_move", "file_delete"})


def lowest_level(tier):
    for level in LADDER:
        if tier in PERMISSIONS[level]:
            return level
    return None


def _definitions():
    seen = {}
    for d in INTENT_PATTERNS:
        seen.setdefault(d["intent"], d)
    seen.setdefault("forget", {"intent": "forget", "description": "Forget something", "tier": 2})
    from logic.file_tools import TOOLS as _FT, DESCRIPTION as _FD
    for n in _FT:
        seen.setdefault(n, {"intent": n, "description": _FD[n], "tier": 2})
    return list(seen.values())


def tool(d):
    name = d["intent"]
    args = ARGS[name]
    props = {a: dict(schema) for a, schema in args}
    tier = d["tier"]
    return {
        "name": name,
        "title": d["description"],
        "description": d["description"] + ".",
        "inputSchema": {"type": "object", "properties": props,
                        "required": [a for a, _ in args], "additionalProperties": False},
        "annotations": {
            "title": d["description"],
            "readOnlyHint": tier == 1 and name not in DESTRUCTIVE,
            "destructiveHint": name in DESTRUCTIVE,
            "idempotentHint": tier == 1 or name == "todo_clear",
            "openWorldHint": False,
        },
        "_meta": {
            "aetherseed/tier": tier,
            "aetherseed/lowest_level": lowest_level(tier),
            "aetherseed/said_by": "unit" if name in SAID_BY_THE_UNIT else "model",
            "aetherseed/routed_by": "patterns",
        },
    }


def manifest():
    return {"tools": [tool(d) for d in _definitions()]}
