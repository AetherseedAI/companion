"""The living journal (logic/journal.py; plan-living-journal, 14 Nov 2026)."""
import os
import shutil
import tempfile
import threading
import unittest

from aetherroot import AetherRoot
from logic import journal as J


def root_in(folder, memory="journal"):
    import json
    with open(os.path.join(folder, "config.json"), "w") as f:
        json.dump({"memory": memory}, f)
    return AetherRoot(folder)


class TheFile(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="jr-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_an_entry_is_one_line_and_reads_back(self):
        j = J.Journal(self.dir)
        n = j.append("steward", "My dog is called Pim.\nHe is · four", at="2026-11-14T10:00:00+00:00")
        self.assertEqual(n, 1)
        lines = open(j.path, encoding="utf-8").read().splitlines()
        self.assertEqual(lines[0], "# Journal")
        self.assertEqual(lines[1], "- #1 · 2026-11-14T10:00:00+00:00 · steward · - · "
                                   "said: My dog is called Pim. He is - four · she: answered")
        e = J.Journal(self.dir).entries[0]
        self.assertEqual((e["n"], e["speaker"], e["said"], e["mode"], e["private"]),
                         (1, "steward", "My dog is called Pim. He is - four", "factual", False))

    def test_flags(self):
        j = J.Journal(self.dir)
        j.append("steward", "a secret", private=True)
        j.append("steward", "write a story", mode="fiction")
        e = J.Journal(self.dir).entries
        self.assertTrue(e[0]["private"])
        self.assertEqual(e[1]["mode"], "fiction")
        self.assertIn("made up", e[1]["did"])

    def test_only_ever_added_to(self):
        j = J.Journal(self.dir)
        j.append("steward", "one")
        before = open(j.path, "rb").read()
        j.append("steward", "two")
        self.assertTrue(open(j.path, "rb").read().startswith(before))

    def test_a_half_written_line_is_left_and_not_read(self):
        j = J.Journal(self.dir)
        j.append("steward", "one")
        with open(j.path, "ab") as f:
            f.write("- #2 · 2026-11-14T10:00:00+00:00 · stew".encode())     # the power went
        j2 = J.Journal(self.dir)
        self.assertEqual(len(j2.entries), 1)
        self.assertEqual(j2.append("steward", "two"), 2)
        j3 = J.Journal(self.dir)
        self.assertEqual([e["said"] for e in j3.entries], ["one", "two"])
        self.assertIn("· stew\n", open(j.path, encoding="utf-8").read())

    def test_who_writes_an_entry(self):
        for who in ("steward", "owner", "linea", ""):
            self.assertTrue(J.writes_an_entry(who, "factual"), who)
        for who in ("Reader", "Trainer", "Haven", "Claude"):
            self.assertFalse(J.writes_an_entry(who, "factual"), who)
        self.assertFalse(J.writes_an_entry("steward", "cog"))
        self.assertFalse(J.writes_an_entry("steward", "factual", training=True))


class TheRings(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="jr-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def fill(self, j, n, start=0):
        topics = ["the garden needs water", "the bees are swarming", "bread is rising slowly",
                  "the boat leaks at the stern"]
        for i in range(start, start + n):
            j.append("steward", "%s today, note %d" % (topics[(i // 12) % 4], i))

    def test_twelve_entries_close_a_ring_entry(self):
        j = J.Journal(self.dir)
        self.fill(j, 11)
        self.assertEqual(len(j.ring_entries), 0)
        self.fill(j, 1, start=11)
        self.assertEqual(len(j.ring_entries), 1)
        r = j.ring_entries[0]
        self.assertEqual(r["span"], "#1-#12")
        # a word in every entry so far is no theme; the quote is one of them
        self.assertIn("e.g. Steward: “the garden needs water today", r["content"])
        self.fill(j, 12, start=12)
        self.assertIn("themes: ", j.ring_entries[1]["content"])
        self.assertIn("bees", j.ring_entries[1]["content"])

    def test_every_word_of_a_ring_was_said(self):
        j = J.Journal(self.dir)
        self.fill(j, 24)
        said = " ".join(e["said"] for e in j.entries).lower()
        from logic.rings import tokens
        for r in j.ring_entries:
            first = r["content"].split(" · ")[0]
            themes = first.replace("themes: ", "").split(", ") if first.startswith("themes: ") else []
            for w in themes:
                self.assertIn(w, said)

    def test_twenty_ring_entries_close_a_ring_once(self):
        j = J.Journal(self.dir)
        self.fill(j, 239)
        self.assertEqual((len(j.ring_entries), len(j.rings)), (19, 0))
        self.fill(j, 1, start=239)
        self.assertEqual((len(j.ring_entries), len(j.rings)), (20, 1))
        self.assertEqual(j.rings[0]["span"], "e1-e20")
        self.fill(j, 12, start=240)
        self.assertEqual((len(j.ring_entries), len(j.rings)), (21, 1))
        text = open(j.rings_path, encoding="utf-8").read()
        self.assertEqual(text.count("\n= r1 "), 1)
        self.assertEqual(text.count("\n- e"), 21)

    def test_private_and_made_up_entries_do_not_count(self):
        j = J.Journal(self.dir)
        self.fill(j, 11)
        j.append("steward", "a secret about the harbour", private=True)
        j.append("steward", "write a story about a dragon", mode="fiction")
        self.assertEqual(len(j.ring_entries), 0)
        self.fill(j, 1, start=11)
        self.assertEqual(len(j.ring_entries), 1)
        self.assertNotIn("harbour", j.ring_entries[0]["content"])
        self.assertNotIn("dragon", j.ring_entries[0]["content"])

    def test_a_ring_left_unwritten_is_made_up_at_the_next_start(self):
        j = J.Journal(self.dir)
        self.fill(j, 12)
        os.remove(j.rings_path)                       # the power went between the two files
        j2 = J.Journal(self.dir)
        self.assertEqual(len(j2.ring_entries), 1)
        self.assertEqual(j2.ring_entries[0]["content"], j.ring_entries[0]["content"])

    def test_two_writers_at_once(self):
        j = J.Journal(self.dir)
        ts = [threading.Thread(target=self.fill, args=(j, 12, k * 12)) for k in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual([e["n"] for e in j.entries], list(range(1, 49)))
        self.assertEqual(len(J.Journal(self.dir).ring_entries), 4)


class InHerMemory(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="root-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.root = root_in(self.dir)

    def test_her_answer_never_comes_back(self):
        self.root.store_interaction("Which model do you run?",
                                    "I run the Qwen3:1.7b model on a Hailo-10H processor.",
                                    speaker="steward")
        block = self.root.retrieve_context("Which model do you run?")
        self.assertIn("[Journal]", block)
        self.assertIn("Which model do you run?", block)
        self.assertNotIn("1.7b", block)
        self.assertNotIn("AI:", block)
        self.assertNotIn("[Episode]", block)

    def test_what_was_said_to_her_comes_back_by_its_words(self):
        self.root.store_interaction("My dog is called Pim and he is four.", "Noted.", speaker="steward")
        self.root.store_interaction("The boat leaks at the stern.", "I see.", speaker="steward")
        block = self.root.retrieve_context("What is my dog called?")
        self.assertIn("Steward said: My dog is called Pim and he is four.", block)
        self.assertNotIn("she answered", block)
        self.assertNotIn("boat", block)

    def test_the_reader_and_the_trainer_write_nothing(self):
        self.root.store_interaction("Song of Songs 1:7", "…", speaker="Reader")
        self.root.store_interaction("What is 2+2?", "4", speaker="Trainer")
        self.root.store_interaction("homework", "done", speaker="steward", rings=False)
        self.assertEqual(self.root.journal().status()["entries"], 0)
        self.assertEqual(self.root.get_status()["episodes"], 3)      # the record keeps them

    def test_a_story_comes_back_tagged(self):
        self.root.store_interaction("Write a story about a dragon called Ember.", "Once…",
                                    mode="fiction", speaker="steward")
        block = self.root.retrieve_context("Tell me about the dragon Ember", request_mode="factual")
        line = [l for l in block.splitlines() if "Ember" in l][0]
        self.assertIn("[Journal]", line)
        self.assertNotEqual(line.find("["), line.find("[Journal]"))   # a tag stands in front

    def test_rings_come_from_the_journal_and_the_old_ones_are_not_made(self):
        for i in range(60):
            self.root.store_interaction("the garden needs water today, note %d" % i, "ok",
                                        speaker="steward")
        st = self.root.get_status()
        self.assertEqual(st["journal"]["ring_entries"], 5)
        self.assertEqual(st["rings"], {"count": 0, "last_at": None, "into": 5, "of": 20})
        self.assertEqual(self.root.store.get_rings()["count"], 0)
        block = self.root.retrieve_context("How is the garden?")
        self.assertIn("[Ring entry", block)

    def test_a_later_word_on_the_same_thing_says_so(self):
        self.root.store_interaction("My dog is called Pim. He is a four-year-old border terrier.",
                                    "Noted.", speaker="steward")
        for i in range(30):
            self.root.store_interaction("the boat needs paint, note %d" % i, "ok", speaker="steward")
        self.root.store_interaction("Pim had his birthday yesterday, so he is five now.", "ok",
                                    speaker="steward")
        block = self.root.retrieve_context("How old is my dog Pim?")
        lines = [l for l in block.splitlines() if "Pim" in l and "[Journal]" in l]
        self.assertEqual(len(lines), 2, block)
        self.assertIn("said: My dog is called Pim", lines[0])
        self.assertIn("said later: Pim had his birthday", lines[1])
        with open(os.path.join(self.dir, "journal.md"), encoding="utf-8") as f:
            self.assertNotIn("said later", f.read())

    def test_only_a_rare_word_of_the_question_links(self):
        self.root.store_interaction("My dog is called Pim. He is a four-year-old border terrier.",
                                    "Noted.", speaker="steward")
        self.root.store_interaction("Write a four-line poem about rain.", "...", mode="fiction",
                                    speaker="steward")
        block = self.root.retrieve_context("How old is my dog Pim?")
        self.assertNotIn("said later", block)
        self.assertNotIn("poem", block)

    def test_an_unverified_answer_does_not_label_what_was_said(self):
        self.root.store_interaction("Can you focus?", "only when it matters", mode="unverified",
                                    speaker="steward")
        block = self.root.retrieve_context("Can you focus?")
        line = [l for l in block.splitlines() if "focus" in l][0]
        self.assertTrue(line.startswith("- [Journal]"), line)
        self.assertNotIn("only when it matters", block)

    def test_a_guest_is_shown_only_her_own_entries(self):
        self.root.store_interaction("My password hint is the harbour.", "ok", speaker="steward")
        self.root.store_interaction("I like the harbour at dusk.", "ok", speaker="guest")
        block = self.root.retrieve_context("Tell me about the harbour", only_speaker="guest")
        self.assertIn("dusk", block)
        self.assertNotIn("password", block)
        self.assertNotIn("[Ring", block)

    def test_episodes_as_before_when_the_setting_says_so(self):
        d = tempfile.mkdtemp(prefix="root-")
        self.addCleanup(shutil.rmtree, d, True)
        root = root_in(d, memory="episodes")
        root.store_interaction("My dog is called Pim.", "Noted.", speaker="steward")
        self.assertIsNone(root.journal())
        self.assertFalse(os.path.exists(os.path.join(d, "journal.md")))
        self.assertIn("[Episode]", root.retrieve_context("What is my dog called?"))

    def test_what_was_told_on_the_first_day_is_there_after_a_cycle(self):
        self.root.store_interaction("My dog is called Pim.", "Noted.", speaker="steward")
        for i in range(260):
            self.root.store_interaction("the boat called Tern needs paint, note %d" % i, "ok",
                                        speaker="steward")
        self.assertIn("Pim", self.root.retrieve_context("What is my dog called?"))

    def test_it_is_there_after_a_restart(self):
        self.root.store_interaction("My dog is called Pim.", "Noted.", speaker="steward")
        again = root_in(self.dir)
        self.assertIn("Pim", again.retrieve_context("What is my dog called?"))


class TurningItOn(unittest.TestCase):
    """tools/journal.py: seeded once from what people said, never her answers."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="root-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        root = root_in(self.dir, memory="episodes")
        root.store_interaction("My dog is called Pim.", "I run the Qwen3:1.7b model.", speaker="steward")
        root.store_interaction("Song of Songs 1:7", "...", speaker="Reader")
        root.store_interaction("Which model do you run?", "Qwen3:1.7b", speaker="Trainer")
        root.store_interaction("I like the harbour.", "Nice.", speaker="linea")
        root.store.conn.close() if hasattr(root.store, "conn") else None
        self.before = open(os.path.join(self.dir, "memory.db"), "rb").read()

    def run_tool(self, *args):
        import subprocess, sys
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run([sys.executable, os.path.join(here, "tools", "journal.py"), *args],
                              capture_output=True, text=True, check=True).stdout

    def test_on_seeds_once_from_what_people_said(self):
        import json
        out = json.loads(self.run_tool("on", self.dir))
        self.assertEqual((out["memory"], out["seeded_now"], out["entries"]), ("journal", 2, 2))
        text = open(os.path.join(self.dir, "journal.md"), encoding="utf-8").read()
        self.assertIn("said: My dog is called Pim.", text)
        self.assertIn("said: I like the harbour.", text)
        for never in ("1.7b", "Song of Songs", "Which model"):
            self.assertNotIn(never, text)
        self.assertNotIn("Pim", out.__repr__())             # counts only, never words
        again = json.loads(self.run_tool("on", self.dir))
        self.assertEqual((again["seeded_now"], again["entries"]), (0, 2))
        self.assertIn("Pim", root_in_keep(self.dir).retrieve_context("What is my dog called?"))

    def test_off_goes_back_and_keeps_the_journal(self):
        import json
        self.run_tool("on", self.dir)
        out = json.loads(self.run_tool("off", self.dir))
        self.assertEqual(out["memory"], "episodes")
        self.assertTrue(os.path.exists(os.path.join(self.dir, "journal.md")))


class TheRecentPast(unittest.TestCase):
    """The latest statements older than the conversation's window come back
    whatever their words (aetherroot.JOURNAL_RECENT; trial 15 Nov 2026)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="root-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.root = root_in(self.dir)

    def tell(self, *said):
        for x in said:
            self.root.store_interaction(x, "ok", speaker="steward")

    def test_a_fact_past_the_window_comes_back_in_other_words(self):
        import aetherroot as A
        self.tell("My cousin works as a beekeeper.")
        self.tell(*["What is %d plus %d?" % (i, i) for i in range(A.JOURNAL_WINDOW + 2)])
        block = self.root.retrieve_context("What does my relative do for a living?")
        self.assertIn("beekeeper", block)
        self.assertNotIn("plus", block, "a question tells her nothing")

    def test_the_window_itself_is_not_shown_twice(self):
        import aetherroot as A
        self.tell("My cousin works as a beekeeper.")
        block = self.root.retrieve_context("What does my relative do for a living?")
        self.assertNotIn("beekeeper", block, "still in the conversation itself")

    def test_at_most_the_latest_few(self):
        import aetherroot as A
        self.tell(*["Note number %d is about the shed." % i for i in range(A.JOURNAL_RECENT + 10)])
        self.tell(*["Is it %d?" % i for i in range(A.JOURNAL_WINDOW)])
        block = self.root.retrieve_context("Anything new?")
        shown = [l for l in block.splitlines() if "Note number" in l]
        self.assertLessEqual(len(shown), A.JOURNAL_RECENT)
        self.assertIn("Note number %d " % (A.JOURNAL_RECENT + 9), block)
        self.assertNotIn("Note number 0 ", block)

    def test_a_guest_sees_only_her_own(self):
        import aetherroot as A
        self.root.store_interaction("My password hint is the harbour.", "ok", speaker="steward")
        for i in range(A.JOURNAL_WINDOW + 1):
            self.root.store_interaction("Is it %d?" % i, "ok", speaker="steward")
        self.root.store_interaction("I like the sea.", "ok", speaker="guest")
        for i in range(A.JOURNAL_WINDOW + 1):
            self.root.store_interaction("Is it %d?" % i, "ok", speaker="guest")
        block = self.root.retrieve_context("What do I like?", only_speaker="guest")
        self.assertIn("sea", block)
        self.assertNotIn("password", block)


def root_in_keep(folder):
    return AetherRoot(folder)


if __name__ == "__main__":
    unittest.main()
