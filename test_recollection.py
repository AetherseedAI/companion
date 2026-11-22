"""A question about a past talk her memory knows nothing of gets a line saying so.

    python3 -m unittest test_recollection -v
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aetherroot  # noqa: E402
from logic.recollection import past_topic, nothing_found_line  # noqa: E402

NOTE = "[Nothing in memory]"


class Topic(unittest.TestCase):

    def test_the_topic_of_a_question_about_a_past_talk(self):
        self.assertEqual(past_topic("What did we talk about regarding beekeeping?"), "beekeeping")
        self.assertEqual(past_topic("What did I tell you about my trip to Japan?"), "trip to Japan")
        self.assertEqual(past_topic("What did we discuss about chess openings?"), "chess openings")
        self.assertEqual(past_topic("What did we talk about regarding the observer effect?"),
                         "observer effect")

    def test_other_questions_are_not_about_a_past_talk(self):
        for q in ("What do you know about motorbikes?", "What did I have for breakfast?",
                  "Who was the last king of Rome?", "Hi!", ""):
            self.assertEqual(past_topic(q), "", q)


class Block(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="recall-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.root = aetherroot.AetherRoot(self.home)
        self.root.config["semantic_memory"] = False
        self.root.store_interaction("Great, what do you know about building with stones",
                                    "Stone is durable.", speaker="steward")

    def test_a_talk_that_never_happened_is_said_to_be_absent(self):
        rep = {}
        ctx = self.root.retrieve_context("What did we talk about regarding beekeeping?", report=rep)
        self.assertIn(NOTE, ctx)
        self.assertIn('"beekeeping"', ctx)
        self.assertTrue(ctx.startswith("[MEMORY CONTEXT]") and ctx.endswith("[END MEMORY CONTEXT]"))
        self.assertEqual(rep.get("nothing_found"), "beekeeping")
        self.assertNotIn(NOTE, rep.get("trusted_context", ""))

    def test_a_talk_that_did_happen_is_not(self):
        # by words "stonework" does not bring "building with stones" back
        # (by meaning it does); either way the store has it, so no line says
        # it has nothing
        self.assertNotIn(NOTE, self.root.retrieve_context("What did we talk about regarding stonework?"))
        self.assertNotIn(NOTE, self.root.retrieve_context("What did we talk about regarding stones?"))

    def test_every_stem_of_the_topic_must_be_found_together(self):
        self.root.store_interaction("What did Melchizedek bring out?", "Bread and wine.")
        self.assertIn(NOTE, self.root.retrieve_context("What did we talk about regarding sourdough bread?"))

    def test_a_question_not_about_a_past_talk_gets_no_line(self):
        self.assertNotIn(NOTE, self.root.retrieve_context("What do you know about beekeeping?"))
        self.assertNotIn(NOTE, self.root.retrieve_context("Hi!"))

    def test_the_line_says_only_what_is_true_of_the_store(self):
        line = nothing_found_line("beekeeping")
        self.assertIn("No turn in your memory is about", line)
        self.assertIn("say so", line)


if __name__ == "__main__":
    unittest.main()
