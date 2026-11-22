"""Who she is talking with, and whether she is online: the unit says it.

    python3 -m unittest test_identity_routes -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_step86 import Pipeline, SCRIPT, proxy  # noqa: E402
from logic import companion, knowledge as K  # noqa: E402
from logic.prompt_builder import charter  # noqa: E402


class TheQuestions(unittest.TestCase):

    def test_cloud(self):
        for q in ("Are you connected to the cloud?", "are you in the cloud", "Do you use the cloud?"):
            self.assertEqual(K.exact_entry_for(q), K.CLOUD_ENTRY, q)

    def test_online(self):
        for q in ("Are you online?", "Can you go online?", "Are you connected to the internet?"):
            self.assertEqual(K.exact_entry_for(q), K.ONLINE_ENTRY, q)

    def test_who_am_i(self):
        for q in ("Do you know who I am?", "Who am I?", "What's my name?"):
            self.assertTrue(K.is_who_am_i_question(q), q)

    def test_not_these(self):
        for q in ("Tell me about cloud computing.", "What is the internet?",
                  "Do you know who I am meeting tomorrow?", "Who am I to judge?"):
            self.assertIsNone(K.exact_entry_for(q), q)
            self.assertFalse(K.is_who_am_i_question(q), q)

    def test_the_lines_exist(self):
        k = K.load_knowledge()
        self.assertTrue(k.by_id(K.CLOUD_ENTRY))
        self.assertTrue(k.by_id(K.ONLINE_ENTRY))


class TheCharter(unittest.TestCase):

    def test_no_line_to_recite_about_the_hardware(self):
        c = charter("Aria", "en", "Ada")
        for gone in ("Raspberry Pi", "Hailo", "small, local, and honest", "local AI companion"):
            self.assertNotIn(gone, c)
        self.assertIn("never claim an ability you lack", c)
        self.assertIn("Never invent facts", c)


class AtTheProxy(Pipeline):
    level = "observer"

    def setUp(self):
        super().setUp()
        companion.save(proxy.COMPANION_FILE, "Aria", "en", "Ada")

    def test_the_steward_is_named_to_the_steward(self):
        n = len(SCRIPT["requests"])
        self.assertEqual(self.chat("Do you know who I am?"), "You are Ada, my steward.")
        self.assertEqual(len(SCRIPT["requests"]), n, "the model is not called")

    def test_a_guest_is_not_told_he_is_the_steward(self):
        self.assertNotIn("Ada", self.chat("Do you know who I am?", guest=True))

    def test_the_cloud_question_is_answered_from_the_build(self):
        n = len(SCRIPT["requests"])
        reply = self.chat("Are you connected to the cloud?")
        self.assertEqual(reply, K.load_knowledge().by_id(K.CLOUD_ENTRY))
        self.assertEqual(len(SCRIPT["requests"]), n)


if __name__ == "__main__":
    unittest.main()
