"""Loops and a dash seen on the Hailo chip (a unit, 16 Nov 2026), never on a PC.

  - "It is a tag. It is a tag. It is a tag." - a short sentence said again and
    again: too short for the repeat stop's 16 characters.
  - "I did not eat for breakfast on the third of March - I did not eat for
    breakfast on the third of March - ..." - the parts are joined by dashes,
    so no sentence ever closed for the repeat stop to see.
  - "You didn't mention your cat's name - It's not a fact." - an honest
    decline that ends in a dash: the decline stop waited for a full stop and
    the tic came after it.
"""
import unittest

from logic.token_budget import repeat_hold
from logic import decline_stop as D
from test_memory_turn import SCRIPT, _Proxy


class ShortLoops(unittest.TestCase):

    def test_a_short_sentence_said_again_in_one_answer_ends_it(self):
        t = "A tag on one of my memories means: It is a label. It is a tag. It is a tag."
        hold, cut, again = repeat_hold(t)
        self.assertTrue(again)
        self.assertEqual(t[:cut].rstrip(), "A tag on one of my memories means: It is a label. It is a tag.")

    def test_very_short_answers_may_still_repeat(self):
        self.assertEqual(repeat_hold("Yes. Yes."), (0, None, False))
        self.assertEqual(repeat_hold("No, no. No, no."), (0, None, False))

    def test_a_short_sentence_of_an_earlier_answer_is_not_left_out(self):
        # only a loop inside one answer counts this short
        self.assertEqual(repeat_hold("It is a tag. Tags mark things.", {"it is a tag"}), (0, None, False))


class DashLoops(unittest.TestCase):

    def test_parts_joined_by_dashes_repeat(self):
        part = "I did not eat for breakfast on the third of March"
        t = part + " — " + part + " — "
        hold, cut, again = repeat_hold(t)
        self.assertTrue(again)
        self.assertEqual(t[:cut].rstrip(" —"), part)

    def test_a_single_dash_goes_out(self):
        t = "Rain is good for the garden — the soil drinks it slowly."
        self.assertEqual(repeat_hold(t), (0, None, False))


class DeclineEndsInADash(unittest.TestCase):

    def test_a_decline_closed_by_a_dash_ends_the_answer(self):
        self.assertTrue(D.stop_here("What is my cat's name?", "You didn't mention your cat's name —", " It"))
        self.assertTrue(D.stop_here("How old is my sister?", "I don't know how old your sister is –", "\n"))

    def test_a_dash_inside_a_statement_does_not(self):
        self.assertFalse(D.stop_here("What did I eat for breakfast?",
                                     "You didn't eat for breakfast on the third of March —", " It"))
        self.assertFalse(D.stop_here("Why is the sky blue?", "I'm not sure —", " light"))


class InTheStream(_Proxy):

    def test_the_tic_after_a_dash_decline_is_never_sent(self):
        SCRIPT["chunks"] = ["You didn't", " mention your", " cat's name —", " It's", " not a fact."]
        status, reply, meta = self.ask("What is my cat's name?")
        self.assertEqual(status, 200)
        self.assertIn("You didn't mention your cat's name", reply)
        self.assertNotIn("not a fact", reply)

    def test_a_short_loop_is_said_once(self):
        SCRIPT["chunks"] = ["A tag", " marks a memory.", " It is a tag.", " It is", " a tag.", " It is a tag."]
        status, reply, meta = self.ask("What does a tag on one of your memories mean?")
        self.assertEqual(reply.count("It is a tag"), 1, reply)


if __name__ == "__main__":
    unittest.main()
