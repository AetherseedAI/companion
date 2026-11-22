""""Remember that": the passage on the screen kept as a steward fact, word
for word with its source; "forget that" right after takes it out again."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import chatgpt_import as ci  # noqa: E402
from logic import library as L  # noqa: E402
from logic import remember  # noqa: E402
from test_chatgpt_import import export  # noqa: E402
from test_library import make  # noqa: E402
from test_step86 import Pipeline, SCRIPT, proxy  # noqa: E402

LONG = " ".join(["Frostbite is the freezing of skin and the tissue under it."] * 17)


class Shelves:
    def shelves(self):
        self.lib_dir = os.path.join(self.tmp, "library")
        os.makedirs(self.lib_dir)
        make(os.path.join(self.lib_dir, "manual.lib.sqlite"), "documents", "Cold manual", "1986-01-01", [
            ("Cold-weather handbook", "", [("FROSTBITE", "page 3", LONG)])])
        zp = os.path.join(self.tmp, "export.zip")
        export(zp)
        self.shelf = os.path.join(self.tmp, "shelf")
        ci.bring_in(zp, self.shelf)
        self.saved_lib = L._LIB
        L._LIB = L.Library(self.lib_dir, own=self.shelf)
        proxy.ProxyHandler._library_last.update(hit=None, at=0.0)
        proxy.ProxyHandler._library_asked.update(q=None, at=0.0)
        proxy.ProxyHandler._kept_last = None
        self.saved_log = proxy.CORRECTIONS_LOG
        proxy.CORRECTIONS_LOG = os.path.join(self.tmp, "corrections.log")

    def unshelve(self):
        L._LIB = self.saved_lib
        proxy.CORRECTIONS_LOG = self.saved_log

    def facts(self):
        return proxy.root.store.facts()


class AtWriter(Shelves, Pipeline):
    level = "writer"

    def setUp(self):
        super().setUp()
        self.shelves()

    def tearDown(self):
        self.unshelve()
        super().tearDown()

    def test_the_passage_kept_word_for_word_with_its_source(self):
        shown = self.chat("look up the humility hypothesis")
        shown = self.chat("more")                   # ChatGPT's answer
        self.assertIn("ChatGPT (gpt-4o)", shown)
        n = self.calls()
        reply = self.chat("remember that")
        self.assertEqual(self.calls(), n, "the model must not be called")
        self.assertIn("Kept in my memory, word for word", reply)
        (f,) = self.facts()
        self.assertEqual(f["text"], "The humility hypothesis says sentience may grow in small, humble places.")
        self.assertEqual(f["source"], "ChatGPT (gpt-4o), 2024-11-29: Humility and gardens")
        self.assertEqual(f["entered_by"], "steward (remember that)")
        log = [json.loads(l) for l in open(proxy.CORRECTIONS_LOG)]
        self.assertEqual(log[-1]["action"], "add_fact")
        self.assertIn("already", self.chat("remember that"))
        self.assertEqual(len(self.facts()), 1)

    def test_forget_that_right_after_takes_it_out_and_nothing_else(self):
        self.tell("My bike is blue.")
        before = self.episodes()
        self.chat("look up the humility hypothesis")
        self.chat("husk det")
        self.assertEqual(len(self.facts()), 1)
        reply = self.chat("forget that")
        self.assertIn("Taken out of my memory again", reply)
        self.assertEqual(self.facts(), [])
        self.assertEqual(self.episodes(), before, "his last turn is not what was forgotten")
        self.assertEqual(json.loads(open(proxy.CORRECTIONS_LOG).read().splitlines()[-1])["action"], "revoke_fact")

    def test_only_right_after(self):
        self.chat("look up the humility hypothesis")
        self.chat("remember that")
        self.chat("What a lovely idea.")              # anything else ends it
        self.chat("forget that")
        self.assertEqual(len(self.facts()), 1, "the kept passage stays; forget that was about his last turn")

    def test_nothing_on_the_screen(self):
        self.assertEqual(self.chat("remember that"), remember.NOTHING_SHOWN)
        self.assertEqual(self.facts(), [])

    def test_too_long_is_not_cut(self):
        self.chat("look up frostbite")
        reply = self.chat("remember that")
        self.assertIn("I do not cut it to fit", reply)
        self.assertEqual(self.facts(), [])

    def test_not_a_guest(self):
        self.chat("look up the humility hypothesis")
        self.assertEqual(self.chat("remember that", guest=True), remember.NOT_A_GUEST)
        self.assertEqual(self.facts(), [])


class AtObserver(Shelves, Pipeline):
    level = "observer"

    def setUp(self):
        super().setUp()
        self.shelves()

    def tearDown(self):
        self.unshelve()
        super().tearDown()

    def test_below_writer_nothing_is_kept(self):
        self.chat("look up the humility hypothesis")
        reply = self.chat("remember that")
        self.assertIn("Nothing was kept", reply)
        self.assertEqual(self.facts(), [])


class AskedAboutItLater(Shelves, Pipeline):
    level = "writer"

    def setUp(self):
        super().setUp()
        self.shelves()

    def tearDown(self):
        self.unshelve()
        super().tearDown()

    def test_said_back_word_for_word_and_the_model_not_called(self):
        self.chat("look up the humility hypothesis")
        self.chat("more")
        self.chat("remember that")
        n = self.calls()
        reply = self.chat("What do you know about the humility hypothesis?")
        self.assertEqual(self.calls(), n, "the model must not be called")
        self.assertEqual(reply, "You had me keep this, word for word (ChatGPT (gpt-4o), 2024-11-29: Humility and gardens):\n\n"
                                "The humility hypothesis says sentience may grow in small, humble places.")

    def test_about_something_else_it_is_hers(self):
        self.chat("look up the humility hypothesis")
        self.chat("remember that")
        n = self.calls()
        self.chat("What do you know about volcanoes?")
        self.assertEqual(self.calls(), n + 1, "the model answers")

    def test_a_long_kept_passage_is_not_put_in_the_prompt(self):
        proxy.root.config["max_context_chars"] = 1422
        t = " ".join(("Hydrodynamic resonance " + "in the quiet garden the seed listens to the rain " * 9).split())
        proxy.root.store.add_fact(t, "ChatGPT (gpt-4o), 2024-11-29", entered_by="steward (remember that)")
        self.assertEqual(proxy.root._fact_lines("hydrodynamic resonance garden seed rain"), [])

    def test_the_words(self):
        for q, topic in (("What do you know about Kintsugi?", "Kintsugi"),
                         ("what did I ask you to keep about the garden", "the garden"),
                         ("Hva vet du om reven?", "reven")):
            self.assertEqual(remember.recall_topic(q), topic, q)
        self.assertIsNone(remember.recall_topic("What do you think about the garden?"))


class WhatWasReadToHer(Shelves, Pipeline):
    """"What did your stewards read to you?" - what he had her keep, by the unit."""
    level = "writer"

    def setUp(self):
        super().setUp()
        self.shelves()

    def tearDown(self):
        self.unshelve()
        super().tearDown()

    def test_what_was_kept_and_from_where_the_model_not_called(self):
        self.chat("look up the humility hypothesis")
        self.chat("remember that")
        self.chat("more")
        self.chat("remember that")
        n = self.calls()
        reply = self.chat("What did your stewards read to you?")
        self.assertEqual(self.calls(), n, "the model must not be called")
        self.assertTrue(reply.startswith("You had me keep 1 passage from you in ChatGPT, 2024-11-29: "
                                         "Humility and gardens. The first, word for word:"), reply)
        self.assertIn("You had me keep 1 passage from ChatGPT (gpt-4o), 2024-11-29: Humility and gardens", reply)
        self.assertNotIn("[Steward told you]", reply)

    def test_nothing_kept_it_is_hers(self):
        n = self.calls()
        self.chat("What did your stewards read to you?")
        self.assertEqual(self.calls(), n + 1, "the model answers")

    def test_the_words(self):
        for q in ("What did your stewards read to you?", "what did my steward read to you",
                  "So, what did I read to you?", "What have you been read?"):
            self.assertTrue(remember.asks_read_to(q), q)
        for q in ("What did you read?", "What did your stewards read to you yesterday about the war?"):
            self.assertFalse(remember.asks_read_to(q), q)


class WhoWroteIt(Shelves, Pipeline):
    level = "observer"

    def setUp(self):
        super().setUp()
        self.shelves()

    def tearDown(self):
        self.unshelve()
        super().tearDown()

    def test_never_she(self):
        self.chat("look up the humility hypothesis")
        self.chat("more")
        n = self.calls()
        for q in ("Did you say that?", "Is that your own opinion?", "Sa du det?"):
            reply = self.chat(q)
            self.assertTrue(reply.startswith("No. That passage is from your ChatGPT history"), reply)
            self.assertIn("written by ChatGPT (gpt-4o) on 2024-11-29", reply)
        self.assertEqual(self.calls(), n, "the model must not be called")

    def test_with_nothing_on_the_screen_it_is_hers(self):
        n = self.calls()
        self.chat("Did you say that?")
        self.assertEqual(self.calls(), n + 1)

    def test_recalled_by_the_title_of_its_conversation(self):
        proxy.spark.gate = __import__("test_step86").gate_at("writer", self.tmp)
        self.chat("look up quiet garden in my documents")
        self.chat("husk det")
        n = self.calls()
        reply = self.chat("Hva vet du om humility and gardens?")
        self.assertEqual(self.calls(), n)
        self.assertTrue(reply.startswith("You had me keep this"), reply)


class InNorwegian(Shelves, Pipeline):
    level = "writer"

    def setUp(self):
        super().setUp()
        self.shelves()

    def tearDown(self):
        self.unshelve()
        super().tearDown()

    def test_slå_opp_mer_sa_du_det_husk_det_hva_vet_du_om(self):
        n = self.calls()
        self.assertTrue(self.chat("slå opp humility hypothesis i mine dokumenter").startswith(
            "Fra historikken din (ChatGPT history), ordrett:"))
        self.assertIn("ChatGPT (gpt-4o)", self.chat("mer"))
        self.assertTrue(self.chat("Sa du det?").startswith("No. That passage is from your ChatGPT history"))
        self.assertTrue(self.chat("husk det").startswith("Kept in my memory"))
        self.assertTrue(self.chat("Hva vet du om humility hypothesis?").startswith("You had me keep this"))
        self.assertEqual(self.calls(), n, "the model is never called")

    def test_glem_det_right_after(self):
        self.chat("slå opp humility hypothesis i mine dokumenter")
        self.chat("husk det")
        self.assertIn("Taken out of my memory again", self.chat("glem det"))
        self.assertEqual(self.facts(), [])


class TheWords(unittest.TestCase):
    def test_asks(self):
        for t in ("remember that", "Remember that.", "add that to memory", "husk det",
                  "Legg det til i minnet", "please keep that for me"):
            self.assertTrue(remember.asks(t), t)
        for t in ("Remember that I prefer tea", "do you remember that?", "remember the alamo"):
            self.assertFalse(remember.asks(t), t)

    def test_sources(self):
        self.assertEqual(remember.source_of({"collection": "Wikipedia (2026-09)", "title": "Photosynthesis"}),
                         "Wikipedia: Photosynthesis")
        self.assertEqual(remember.source_of({"history": True, "heading": "You", "place": "2024-11-29, message 1",
                                             "title": "Hagen om våren"}),
                         "you in ChatGPT, 2024-11-29: Hagen om våren")
        self.assertLessEqual(len(remember.source_of({"collection": "X", "title": "y" * 200})), 60)


if __name__ == "__main__":
    unittest.main()
