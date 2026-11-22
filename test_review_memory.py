"""A review of her memory the steward asked for: corrections attributed to it.

    python3 -m unittest test_review_memory -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aetherroot  # noqa: E402
from logic import steward  # noqa: E402
from logic.provenance import memory_tag  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "tools"))
import review_memory  # noqa: E402


class AReview(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rev-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.root = aetherroot.AetherRoot(self.home)
        self.tid = self.root.store_interaction("When did the roman empire begin",
                                               "The Roman Empire began in 264 BCE.")
        self.log = os.path.join(self.home, "corrections.log")
        self.db = self.root.store.db_path

    def test_the_tag_says_whose_correction_it_is(self):
        tag = memory_tag("factual", {"by": "review", "reason": "detail", "text": "27 BCE."})
        self.assertEqual(tag, "[Corrected in a review your steward asked for - what is true: 27 BCE.]")

    def test_dry_run_changes_nothing(self):
        f = os.path.join(self.home, "c.json")
        json.dump([{"target": "turn", "id": self.tid, "reason": "detail",
                    "text": "The Roman Empire began in 27 BCE."}], open(f, "w"))
        review_memory.main([f, "--reviewer", "Claude", "--db", self.db, "--log", self.log])
        self.assertEqual(self.root.store.notes_by_target("turn"), {})

    def test_applied_it_comes_back_tagged_and_is_not_a_steward_fact(self):
        f = os.path.join(self.home, "c.json")
        json.dump([{"target": "turn", "id": self.tid, "reason": "detail",
                    "text": "The Roman Empire began in 27 BCE."}], open(f, "w"))
        review_memory.main([f, "--reviewer", "Claude", "--db", self.db, "--log", self.log, "--apply"])
        store = aetherroot.MemoryStore(self.db)
        note = store.notes_by_target("turn")[self.tid]["correct"]
        self.assertEqual(note["by"], "review")
        self.assertEqual(store.fact_count(active_only=True), 0)
        with open(self.log) as fh:
            text = fh.read()
        self.assertIn("Claude", text)
        self.assertIn("review of her memory", text)
        ctx = aetherroot.AetherRoot(self.home).retrieve_context("When did the roman empire begin")
        self.assertIn("[Corrected in a review your steward asked for - what is true: "
                      "The Roman Empire began in 27 BCE.]", ctx)


if __name__ == "__main__":
    unittest.main()
