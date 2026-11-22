"""The one-file export: her memory as JSON Lines, no secrets, nothing changed.

    python3 -m unittest test_export -v
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import aetherroot  # noqa: E402
import export  # noqa: E402


class Export(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="export-")
        self.addCleanup(shutil.rmtree, self.home, True)
        root = aetherroot.AetherRoot(os.path.join(self.home, ".aetherseed", "aetherroot"))
        root.config["semantic_memory"] = False
        root.store_interaction("What is a sapling?", "A young tree.", speaker="steward")
        st = os.path.join(self.home, ".aetherseed")
        json.dump({"name": "Aria", "steward": "Ada"}, open(os.path.join(st, "companion.json"), "w"))
        open(os.path.join(st, "cog.token"), "w").write("SECRET-TOKEN")
        open(os.path.join(st, "prompts-2026-10.log"), "w").write("a prompt\n")
        open(os.path.join(st, "corrections.log"), "w").write("a correction\n")
        os.makedirs(os.path.join(st, "training"))
        open(os.path.join(st, "training", "state.json"), "w").write("{}")
        ws = os.path.join(self.home, "aetherseed-workspace")
        os.makedirs(ws)
        open(os.path.join(ws, "todo.md"), "w").write("- fix the bike light\n")
        self.out = os.path.join(self.home, "export.jsonl")

    def lines(self):
        return [json.loads(l) for l in open(self.out, encoding="utf-8")]

    def test_what_is_in_it(self):
        db = os.path.join(self.home, ".aetherseed", "aetherroot", "memory.db")
        before = hashlib.sha256(open(db, "rb").read()).hexdigest()
        export.export(self.home, self.out)
        self.assertEqual(hashlib.sha256(open(db, "rb").read()).hexdigest(), before)
        ls = self.lines()
        self.assertEqual(ls[0]["kind"], "aetherseed-export")
        self.assertEqual(ls[0]["companion"], "Aria")
        self.assertEqual(ls[-1]["kind"], "end")
        turns = [l["row"] for l in ls if l["kind"] == "table" and l["table"] == "episodes"]
        self.assertEqual([t["user_msg"] for t in turns], ["What is a sapling?"])
        self.assertNotIn("embedding", turns[0])
        paths = {l["path"]: l for l in ls if l["kind"] in ("file", "left_out")}
        self.assertEqual(paths["aetherseed-workspace/todo.md"]["text"], "- fix the bike light\n")
        self.assertEqual(paths[".aetherseed/corrections.log"]["kind"], "file")
        for p in (".aetherseed/cog.token", ".aetherseed/prompts-2026-10.log",
                  ".aetherseed/training/state.json", ".aetherseed/aetherroot/memory.db"):
            self.assertEqual(paths[p]["kind"], "left_out", p)
        self.assertNotIn("SECRET-TOKEN", open(self.out, encoding="utf-8").read())

    def test_all_takes_the_logs_but_never_the_token(self):
        export.export(self.home, self.out, include_all=True)
        paths = {l["path"]: l for l in self.lines() if l["kind"] in ("file", "left_out")}
        self.assertEqual(paths[".aetherseed/prompts-2026-10.log"]["kind"], "file")
        self.assertEqual(paths[".aetherseed/training/state.json"]["kind"], "file")
        self.assertEqual(paths[".aetherseed/cog.token"]["kind"], "left_out")
        self.assertNotIn("SECRET-TOKEN", open(self.out, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
