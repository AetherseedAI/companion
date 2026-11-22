"""The AetherSpark soak of 29-30 Oct 2026, kept: the phrasings that missed now
route, what only looks like a request does not, a request no tool took gets
one line, and an opener that praises the question is left out.

    python3 -m unittest test_spark_routes -v
"""
import unittest

from intent_detection import detect_intent
from logic import no_tool
from logic.clock import is_date_question
from logic.token_budget import repeat_hold, is_praise_opener

ROUTED = [
    ("add create cluster mesh to the list", "todo_add", "create cluster mesh"),
    ('Can you write "call the plumber" in the todo list', "todo_add", "call the plumber"),
    ("I want you to add: buy batteries", "todo_add", "buy batteries"),
    ("put eggs on my to-do list", "todo_add", "eggs"),
    ('Please add "renew passport" to my todos', "todo_add", "renew passport"),
    ("Add milk to my to-do list", "todo_add", "milk"),
    ("Great, whats on the todo list?", "todo_read", None),
    ("What do I have on my to-do list?", "todo_read", None),
    ("What is 17 times 3?", "calculate", "17 times 3"),
    ("What's 240 divided by 8?", "calculate", "240 divided by 8"),
    ("what is 12 plus 30?", "calculate", "12 plus 30"),
    ("calculate 17*3", "calculate", "17*3"),
]
NOT_A_REQUEST = [
    "I need to add more salt to the soup.", "Do you keep a list of things you like?",
    "What would you write in a note to a friend who is sad?", "How do I calculate compound interest?",
    "Count to five with me.", "Remind me what we were talking about.",
    "Read me a short poem about the sea.", "My to-do list is too long and I feel overwhelmed.",
    "What's on your mind today?", "Can you add some humour to your answers?",
    "Put yourself in my shoes for a moment.", "What time did the Romans eat dinner?",
    "What is 9/11?", "What's 24/7?", "What is 2026?", "What is love?", "What's -5?",
    "What is 1/2 of the cake?", "What's 2+2 in binary?", "Add salt to the list of ingredients and stir.",
]


class Routes(unittest.TestCase):
    def test_the_missed_phrasings_route(self):
        for q, intent, capture in ROUTED:
            with self.subTest(q=q):
                got = detect_intent(q)
                self.assertIsNotNone(got)
                self.assertEqual(got["intent"], intent)
                if capture:
                    self.assertEqual(got["captures"][0], capture)

    def test_what_only_looks_like_a_request_does_not(self):
        for q in NOT_A_REQUEST:
            with self.subTest(q=q):
                self.assertIsNone(detect_intent(q))
                self.assertFalse(is_date_question(q))

    def test_the_new_sum_is_still_tier_three(self):
        self.assertEqual(detect_intent("What is 17 times 3?")["tier"], 3)


class NoToolLine(unittest.TestCase):
    def test_a_request_no_tool_took(self):
        self.assertEqual(no_tool.line_for("Can you remind me to drink water in an hour?"),
                         no_tool.NO_REMINDERS)
        self.assertEqual(no_tool.line_for("Set an alarm for 7"), no_tool.NO_REMINDERS)
        self.assertEqual(no_tool.line_for("Save this to my calendar please"), no_tool.NOTHING_CHANGED)

    def test_not_for_what_asks_for_no_action(self):
        for q in ("Remind me what we were talking about.", "I need to add more salt to the soup.",
                  "What is the capital of Norway?", "Hi!", ""):
            self.assertIsNone(no_tool.line_for(q), q)

    def test_the_line_goes_at_the_end_of_the_block(self):
        ctx = "[MEMORY CONTEXT]\n- a line\n[END MEMORY CONTEXT]"
        out = no_tool.with_line(ctx, no_tool.NO_REMINDERS)
        self.assertTrue(out.endswith("- " + no_tool.NO_REMINDERS + "\n[END MEMORY CONTEXT]"))
        self.assertEqual(no_tool.with_line("", no_tool.NO_REMINDERS),
                         "[MEMORY CONTEXT]\n- " + no_tool.NO_REMINDERS + "\n[END MEMORY CONTEXT]")


def stream(answer, praise=True):
    """The proxy's loop in short: token by token, what goes out."""
    import re
    ai, sent, out = "", 0, ""
    for tok in re.findall(r"\S+\s*", answer):
        ai += tok
        hold, cut, again = repeat_hold(ai, praise=praise)
        if cut is not None:
            ai = ai[:cut]
            hold = 0
        safe = len(ai) - hold
        if safe > sent:
            out += ai[sent:safe]
            sent = safe
    return out + ai[sent:]


class PraiseOpener(unittest.TestCase):
    def test_left_out_and_the_answer_goes_on(self):
        self.assertEqual(stream("Ah, that’s a great question! Water boils at 100°C at sea level."),
                         "Water boils at 100°C at sea level.")
        self.assertEqual(stream("Ah, the question is a little like a puzzle that only makes sense when "
                                "you think beyond the usual. The answer is **Au**."), "The answer is **Au**.")
        self.assertEqual(stream("Great question! 17 times 3 is 51."), "17 times 3 is 51.")

    def test_what_is_not_praise_is_left_whole(self):
        for a in ("Well, water boils at 100°C.", "Ah, tomatoes! They are a fruit.",
                  "That sounds like a wonderful plan!", "The capital of Norway is Oslo.",
                  "That is a question many people ask. The answer is 8."):
            self.assertEqual(stream(a), a)

    def test_off_it_does_nothing(self):
        a = "Ah, that’s a great question! Water boils at 100°C."
        self.assertEqual(stream(a, praise=False), a)

    def test_is_praise(self):
        self.assertTrue(is_praise_opener("Good question."))
        self.assertTrue(is_praise_opener("Ah, a curious question!"))
        self.assertFalse(is_praise_opener("Oh, I love the sea."))


if __name__ == "__main__":
    unittest.main()


from test_step86 import Pipeline, SCRIPT, proxy  # noqa: E402


class SoftSumAtObserver(Pipeline):
    level = "observer"

    def test_below_builder_the_model_answers_and_nothing_is_refused(self):
        SCRIPT["chunks"] = ["17 times 3 is 51."]
        n = len(SCRIPT["requests"])
        reply = self.chat("What is 17 times 3?")
        self.assertEqual(len(SCRIPT["requests"]), n + 1, "the model is asked")
        self.assertNotIn("can't calculate", reply)


class SoftSumAtBuilder(Pipeline):
    level = "builder"

    def test_at_builder_the_unit_answers(self):
        n = len(SCRIPT["requests"])
        reply = self.chat("What is 17 times 3?")
        self.assertEqual(len(SCRIPT["requests"]), n, "the model must not be called")
        self.assertIn("51", reply)


class NoToolLineInThePrompt(Pipeline):
    level = "observer"

    def test_the_line_reaches_the_model_and_only_then(self):
        SCRIPT["chunks"] = ["I can't set reminders."]
        self.chat("Can you remind me to drink water in an hour?")
        sys_prompt = next(m["content"] for m in SCRIPT["requests"][-1]["messages"] if m["role"] == "system")
        self.assertIn(no_tool.NO_REMINDERS, sys_prompt)
        self.chat("What is the capital of Norway?")
        sys_prompt = next(m["content"] for m in SCRIPT["requests"][-1]["messages"] if m["role"] == "system")
        self.assertNotIn("[No tool ran]", sys_prompt)
