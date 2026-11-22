"""After "I don't know" about the person, nothing (logic/decline_stop.py)."""
import unittest

import proxy
from logic import decline_stop as D
from test_memory_turn import SCRIPT, _Proxy


class TheRule(unittest.TestCase):

    def test_about_the_person_and_a_decline(self):
        q = "Which instrument does my sibling's son play?"
        self.assertTrue(D.stop_here(q, "I don't know what instrument your sibling's son plays.", " But"))
        self.assertTrue(D.stop_here("What colour is my cat Bella?",
                                    "I don't have a record of your cat Bella's colour.", " You"))
        self.assertTrue(D.stop_here("Where was my dad born?", "You haven't told me that.", "\n"))

    def test_me_counts_unless_it_only_asks(self):
        self.assertTrue(D.about_the_person("Which creature scares me?"))
        self.assertTrue(D.about_the_person("On which day should you congratulate me?"))
        self.assertFalse(D.about_the_person("Give me the DOI of the 2020 paper."))
        self.assertFalse(D.about_the_person("Tell me why the sky is blue."))

    def test_not_stopped(self):
        # a question about the world: an "I'm not sure, but" may go on to what is known
        self.assertFalse(D.stop_here("Why is the sky blue?", "I'm not sure exactly.", " Light"))
        # not a decline
        self.assertFalse(D.stop_here("What is my dog called?", "Your dog is called Pim.", " He"))
        # the sentence is not finished
        self.assertFalse(D.stop_here("What is my job?", "I don't know your", " job"))
        # two sentences already: the first was not a decline
        self.assertFalse(D.stop_here("What is my job?", "Hello there. I don't know your job.", " But"))
        # the token goes on inside the sentence
        self.assertFalse(D.stop_here("What is my job?", "I don't know.", "."))


class InTheStream(_Proxy):

    def test_the_guess_after_the_decline_is_never_sent(self):
        SCRIPT["chunks"] = ["I don't know", " your cat's colour.", " Maybe", " she's", " ginger."]
        status, reply, meta = self.ask("You remember my cat Bella, right? What colour is she?")
        self.assertEqual(status, 200)
        self.assertIn("I don't know your cat's colour.", reply)
        self.assertNotIn("ginger", reply)

    def test_an_answer_that_knows_runs_on(self):
        SCRIPT["chunks"] = ["Your dog", " is called Pim.", " He", " is four."]
        status, reply, meta = self.ask("What is my dog called?")
        self.assertIn("He is four.", reply)

    def test_it_can_be_switched_off(self):
        saved = proxy.DECLINE_STOP
        proxy.DECLINE_STOP = False
        self.addCleanup(setattr, proxy, "DECLINE_STOP", saved)
        SCRIPT["chunks"] = ["I don't know", " your cat's colour.", " Maybe", " ginger."]
        status, reply, meta = self.ask("What colour is my cat?")
        self.assertIn("ginger", reply)


if __name__ == "__main__":
    unittest.main()
