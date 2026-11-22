"""A sentence said twice in one answer is not said the second time.

    python3 -m unittest test_repeat_stop -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_step86 import Pipeline, SCRIPT, proxy  # noqa: E402
from logic.token_budget import repeat_hold, sentences_of  # noqa: E402
from logic import companion, steward_file as S  # noqa: E402

LINE = "I'm not a real person, but I'm here to be your companion."


class TheHelper(unittest.TestCase):

    def test_held_while_it_arrives_and_cut_when_it_closes(self):
        t = "I am Pip. " + LINE + " "
        self.assertEqual(repeat_hold(t), (0, None, False))
        self.assertEqual(repeat_hold(t + "I'm not a re")[0], len("I'm not a re"))
        self.assertEqual(repeat_hold(t + LINE), (0, len(t), True))

    def test_a_sentence_of_an_earlier_answer_is_left_out(self):
        said = sentences_of("Hello. " + LINE)
        t = "Sure, here it is. " + LINE
        self.assertEqual(repeat_hold(t, said), (0, len("Sure, here it is. "), False))

    def test_a_new_sentence_goes_out(self):
        t = "I am Pip. " + LINE + " I like rain."
        self.assertEqual(repeat_hold(t), (0, None, False))

    def test_short_sentences_may_repeat(self):
        self.assertEqual(repeat_hold("Yes. Yes."), (0, None, False))


class AtTheProxy(Pipeline):
    level = "observer"

    def test_the_repeat_never_reaches_the_reader(self):
        words = ("I am Pip. " + LINE + " " + LINE + " " + LINE).split(" ")
        SCRIPT["chunks"] = [w + " " for w in words]
        reply = self.chat("Who are you?")
        self.assertEqual(reply.count("real person"), 1, reply)
        self.assertTrue(reply.strip().endswith("companion."), reply)


class AcrossTurns(Pipeline):
    level = "observer"

    def test_her_sentence_of_the_last_answer_is_not_said_again(self):
        SCRIPT["chunks"] = [w + " " for w in ("I am Pip. " + LINE).split(" ")]
        self.chat("Who are you?")
        SCRIPT["chunks"] = [w + " " for w in ("Tomatoes are fruit. " + LINE + " They grow in summer.").split(" ")]
        reply = self.chat("Tell me about tomatoes.")
        self.assertNotIn("real person", reply)
        self.assertIn("Tomatoes are fruit.", reply)
        self.assertIn("They grow in summer.", reply)
        self.assertNotIn("  ", reply)


class StockOpeners(Pipeline):
    level = "observer"

    def setUp(self):
        super().setUp()
        self._flag = proxy.CUT_REPEATED_OPENERS
        self.addCleanup(setattr, proxy, "CUT_REPEATED_OPENERS", self._flag)
        self.addCleanup(setattr, proxy, "CUT_PRAISE_OPENERS", proxy.CUT_PRAISE_OPENERS)

    def two(self, second):
        SCRIPT["chunks"] = [w + " " for w in "That's a great question! 17 times 3 is 51.".split(" ")]
        self.chat("What is 17 times 3?")
        SCRIPT["chunks"] = [w + " " for w in second.split(" ")]
        return self.chat("What is 12 plus 30?")

    def test_off_by_default(self):
        proxy.CUT_PRAISE_OPENERS = False
        self.assertIn("great question", self.two("That's a great question! 12 plus 30 is 42."))

    def test_an_opener_that_praises_the_question_is_left_out_by_default(self):
        # 30 Oct 2026 (steward's yes): the first time too
        self.assertTrue(proxy.CUT_PRAISE_OPENERS)
        SCRIPT["chunks"] = [w + " " for w in "Ah, a curious question! 17 times 3 is 51.".split(" ")]
        self.assertEqual(self.chat("What is 17 times 3?").strip(), "17 times 3 is 51.")

    def test_praise_alone_is_never_left_empty(self):
        SCRIPT["chunks"] = [w + " " for w in "That's a great question!".split(" ")]
        self.assertEqual(self.chat("Hi there").strip(), "That's a great question!")

    def test_a_short_answer_with_no_full_stop_is_not_held_back(self):
        SCRIPT["chunks"] = [w + " " for w in "Good morning, Claude".split(" ")]
        self.assertEqual(self.chat("Hi there").strip(), "Good morning, Claude")

    def test_on_the_opener_said_before_is_left_out(self):
        proxy.CUT_REPEATED_OPENERS = True
        reply = self.two("That's a great question! 12 plus 30 is 42.")
        self.assertNotIn("great question", reply)
        self.assertEqual(reply.strip(), "12 plus 30 is 42.")

    def test_on_an_answer_is_never_left_empty(self):
        proxy.CUT_REPEATED_OPENERS = True
        self.assertEqual(self.two("That's a great question!").strip(), "That's a great question!")


class ADeclaredSpeakerIsNotTheSteward(Pipeline):
    level = "observer"

    def setUp(self):
        super().setUp()
        companion.save(proxy.COMPANION_FILE, "Aria", "en", "Ada")

    def chat_as(self, text, speaker):
        import http.client
        import json
        body = {"model": "x", "stream": True, "speaker": speaker,
                "messages": [{"role": "user", "content": text}]}
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=30)
        c.request("POST", "/api/chat", body=json.dumps(body),
                  headers={"Content-Type": "application/json"})
        raw = c.getresponse().read().decode()
        c.close()
        lines = [json.loads(l) for l in raw.split("\n") if l.strip()]
        return "".join((l.get("message") or {}).get("content", "") for l in lines)

    def test_not_told_he_is_the_steward(self):
        reply = self.chat_as("Do you know who I am?", "Claude")
        self.assertNotIn("You are Ada", reply)
        self.assertEqual(reply, "You told me you are Claude.")

    def test_cannot_write_the_steward_file_nor_see_it_in_the_prompt(self):
        S.add(self.ws, S.PREFS, "I prefer short answers")
        self.chat_as("Remember that I prefer long answers.", "Claude")
        self.assertEqual(S.items(self.ws)[S.PREFS], ["I prefer short answers"])
        self.chat_as("Tell me about gardens.", "Claude")
        self.assertNotIn("I prefer short answers", SCRIPT["requests"][-1]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
