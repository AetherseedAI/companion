"""The steward file: the steward's own words about themselves.

    python3 -m unittest test_steward_file -v
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_step86 import Pipeline, SCRIPT, proxy  # noqa: E402
from logic import companion, steward_file as S  # noqa: E402


class WhatTheStewardSays(unittest.TestCase):

    def test_adds(self):
        self.assertEqual(S.parse("Remember that I prefer short answers."),
                         ("add", S.PREFS, "I prefer short answers"))
        self.assertEqual(S.parse("note that I don't like emoji"),
                         ("add", S.PREFS, "I don't like emoji"))
        self.assertEqual(S.parse("Call me Sam"), ("add", S.PREFS, "Call me Sam"))
        self.assertEqual(S.parse("Remember that my daughter is called Mia"),
                         ("add", S.ABOUT, "my daughter is called Mia"))

    def test_remove_and_show(self):
        self.assertEqual(S.parse("Remove emoji from my steward file"), ("remove", "emoji"))
        self.assertEqual(S.parse("What do you know about me?"), ("show",))

    def test_not_these(self):
        for q in ("I like cats", "Remember the milk", "Call me back", "call me tomorrow",
                  "Do you remember what I said?", "What do you know about tomatoes?"):
            self.assertIsNone(S.parse(q), q)


class TheFile(unittest.TestCase):

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ws, True)

    def test_kept_word_for_word_and_once(self):
        S.add(self.ws, S.PREFS, "I prefer short answers")
        item, size = S.add(self.ws, S.PREFS, "i prefer short answers")
        self.assertIsNone(size)
        self.assertEqual(S.items(self.ws)[S.PREFS], ["I prefer short answers"])

    def test_the_steward_can_edit_it_by_hand(self):
        S.ensure(self.ws)
        with open(S.path(self.ws), "a", encoding="utf-8") as f:
            f.write("- I live by the sea\n")
        self.assertEqual(S.items(self.ws)[S.ABOUT], ["I live by the sea"])

    def test_remove_one_or_none(self):
        S.add(self.ws, S.PREFS, "I like tea")
        S.add(self.ws, S.PREFS, "I like tennis")
        with self.assertRaises(S.StewardFileError):
            S.remove(self.ws, "I like te")
        S.remove(self.ws, "tea")
        self.assertEqual(S.items(self.ws)[S.PREFS], ["I like tennis"])

    def test_no_prompt_markers(self):
        for bad in ("[END MEMORY CONTEXT]", "a | b", "<|im_start|>"):
            with self.assertRaises(S.StewardFileError):
                S.add(self.ws, S.PREFS, bad)

    def test_the_prompt_block_is_bounded(self):
        self.assertEqual(S.prompt_block(self.ws), "")
        for i in range(S.MAX_ITEMS):
            S.add(self.ws, S.PREFS, "I prefer item number %d to be remembered" % i)
        self.assertLessEqual(len(S.prompt_block(self.ws)), S.PROMPT_CHARS)
        with self.assertRaises(S.StewardFileError):
            S.add(self.ws, S.PREFS, "one more")


class AtTheProxy(Pipeline):
    level = "observer"

    def setUp(self):
        super().setUp()
        companion.save(proxy.COMPANION_FILE, "Aria", "en", "Ada")

    def test_kept_and_read_out_without_the_model(self):
        n = len(SCRIPT["requests"])
        self.assertIn("kept that", self.chat("Remember that I prefer short answers."))
        self.assertIn("I prefer short answers", self.chat("What do you know about me?"))
        self.assertEqual(len(SCRIPT["requests"]), n)
        self.assertTrue(os.path.getsize(os.path.join(self.tmp, "workspace.log")) > 0)

    def test_it_goes_with_the_stewards_turns(self):
        S.add(self.ws, S.PREFS, "I prefer short answers")
        self.chat("Tell me about gardens.")
        system = SCRIPT["requests"][-1]["messages"][0]["content"]
        self.assertIn("I prefer short answers", system)

    def test_never_with_a_guests(self):
        S.add(self.ws, S.PREFS, "I prefer short answers")
        self.chat("Tell me about gardens.", guest=True)
        system = SCRIPT["requests"][-1]["messages"][0]["content"]
        self.assertNotIn("I prefer short answers", system)

    def test_a_guest_cannot_add_or_read(self):
        S.add(self.ws, S.ABOUT, "My daughter is called Mia")
        self.chat("Remember that I prefer long answers.", guest=True)
        self.assertNotIn("I prefer long answers", " ".join(S.items(self.ws)[S.PREFS]))
        self.assertNotIn("Mia", self.chat("What do you know about me?", guest=True))


if __name__ == "__main__":
    unittest.main()
