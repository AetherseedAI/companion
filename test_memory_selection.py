"""Which memories go with a question: what it is about, not small talk.

    python3 -m unittest test_memory_selection -v
"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aetherroot  # noqa: E402

LINE = "I'm running Sam, a companion who guides through message, memory, and meaning."


class Selection(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sel-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.root = aetherroot.AetherRoot(self.home)
        self.root.store_interaction("thanks", "You're welcome, " + LINE)
        self.root.store_interaction("Training round 17: how many times did the rooster crow?", "Three times.", speaker="Trainer")
        self.root.store_interaction("Review of your essay: interesting insight", "Thank you.",
                                    speaker="Trainer")
        self.root.store_interaction("what are the origins of the roman republic",
                                    "Rome was ruled by kings before the republic.")
        st = self.root.store
        ring = st.store_semantic("themes: message, lantern, running, harbour, companion · e.g. "
                                 "Steward: “I want to talk about life and gratitude”",
                                 np.zeros(64, dtype=np.float32), [1], 0.9, 0.9, ring_no=1)
        st.conn.execute("UPDATE semantic SET own_words = ? WHERE id = ?", (LINE, ring))
        st.store_semantic("themes: king, last, roman, republic · e.g. Steward: “what are the "
                          "origins of the roman republic”",
                          np.zeros(64, dtype=np.float32), [4], 0.9, 0.9, ring_no=2)
        st.conn.commit()

    def ctx(self, q):
        return self.root.retrieve_context(q)

    def test_a_greeting_brings_no_ring(self):
        self.assertNotIn("[Ring]", self.ctx("Hi!"))
        self.assertNotIn("running Sam", self.ctx("Hi!"))

    def test_thanks_does_not_bring_back_an_old_thanks(self):
        self.assertNotIn("running Sam", self.ctx("Thanks, that's all for now."))

    def test_a_number_is_not_a_topic(self):
        self.assertNotIn("round 17", self.ctx("What is 17 times 3?"))
        self.assertNotIn("rooster", self.ctx("What is 17 times 3?"))

    def test_small_talk_words_are_not_a_topic(self):
        self.assertNotIn("essay", self.ctx("Tell me something interesting about tomatoes."))

    def test_a_question_on_a_rings_subject_still_brings_it(self):
        c = self.ctx("Tell me about the roman republic and its last king")
        self.assertIn("[Ring] 2", c)
        self.assertNotIn("[Ring] 1", c)

    def test_her_own_words_do_not_pull_the_ring(self):
        self.assertNotIn("[Ring] 1", self.ctx("What does memory and meaning mean to you?"))

    def test_her_own_words_are_not_shown_with_the_ring(self):
        st = self.root.store
        st.conn.execute("UPDATE semantic SET own_words = ? WHERE ring_no = 2",
                        ("Rome was ruled by a biological process leaking into memory.",))
        st.conn.commit()
        c = self.ctx("Tell me about the roman republic and its last king")
        self.assertIn("[Ring] 2", c)
        self.assertNotIn("biological process", c)


if __name__ == "__main__":
    unittest.main()
