"""Her tools described in the MCP shape: every routed tool, and nothing more.

    python3 -m unittest test_tool_manifest -v
"""
import json
import unittest

from intent_detection import INTENT_PATTERNS
from logic.levels import PERMISSIONS
from logic.tool_manifest import manifest, NAME, ARGS


class Manifest(unittest.TestCase):
    def setUp(self):
        self.tools = {t["name"]: t for t in manifest()["tools"]}

    def test_every_routed_tool_and_forget_is_described_once(self):
        from logic.file_tools import TOOLS as FILE_TOOLS       # read by parse(), not patterns
        names = {d["intent"] for d in INTENT_PATTERNS} | {"forget"} | set(FILE_TOOLS)
        self.assertEqual(set(self.tools), names)
        self.assertEqual(len(manifest()["tools"]), len(names))
        self.assertEqual(set(ARGS), names)

    def test_the_shape(self):
        for name, t in self.tools.items():
            with self.subTest(name=name):
                self.assertRegex(name, NAME)
                self.assertTrue(t["description"])
                s = t["inputSchema"]
                self.assertEqual(s["type"], "object")
                self.assertEqual(set(s["required"]), set(s["properties"]))
                self.assertFalse(t["annotations"]["openWorldHint"])
        json.dumps(manifest())

    def test_the_tier_and_its_lowest_level(self):
        for name, t in self.tools.items():
            tier = t["_meta"]["aetherseed/tier"]
            level = t["_meta"]["aetherseed/lowest_level"]
            self.assertIn(tier, PERMISSIONS[level], name)
        self.assertEqual(self.tools["todo_add"]["_meta"]["aetherseed/lowest_level"], "writer")
        self.assertEqual(self.tools["calculate"]["_meta"]["aetherseed/lowest_level"], "builder")
        self.assertEqual(self.tools["file_read"]["_meta"]["aetherseed/lowest_level"], "observer")

    def test_writes_are_not_read_only_and_removals_are_destructive(self):
        for name in ("todo_add", "note_write", "todo_remove", "todo_clear", "forget"):
            self.assertFalse(self.tools[name]["annotations"]["readOnlyHint"], name)
        for name in ("todo_remove", "todo_clear", "todo_edit", "forget", "file_move", "file_delete"):
            self.assertTrue(self.tools[name]["annotations"]["destructiveHint"], name)
        for name in ("file_save", "file_append", "file_write", "folder_make"):
            self.assertFalse(self.tools[name]["annotations"]["readOnlyHint"], name)
            self.assertEqual(self.tools[name]["_meta"]["aetherseed/lowest_level"], "writer")
        self.assertTrue(self.tools["file_read"]["annotations"]["readOnlyHint"])

    def test_the_arguments_are_the_captures_in_order(self):
        for d in INTENT_PATTERNS:
            for p in d["patterns"]:
                import re
                groups = re.compile(p).groups
                if d["intent"] == "note_write" and groups == 0:
                    continue        # "save this as a note": the message itself is the note
                self.assertEqual(groups, len(ARGS[d["intent"]]), (d["intent"], p))


if __name__ == "__main__":
    unittest.main()
