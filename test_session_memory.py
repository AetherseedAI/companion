"""The conversation in progress, held in RAM on the unit (logic/working_memory):
drawn again by the console after a refresh, kept across a restart of the
proxy through its folder in /run, one person's only, and with more of it in a
prompt for a model with room for it (the steward, 13 Nov)."""
import json
import os
import re
import shutil
import tempfile
import unittest

from logic import working_memory as wm
from logic.working_memory import WorkingMemory, max_exchanges_for

HERE = os.path.dirname(os.path.abspath(__file__))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TheSession(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="session-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.clock = Clock()

    def make(self, folder=True):
        return WorkingMemory(clock=self.clock, wall=lambda: 1.7e9 + self.clock.t,
                             folder=self.dir if folder else None)

    def test_a_restart_of_the_proxy_keeps_the_talk(self):
        a = self.make()
        a.add("Ada", "My sister moves on Saturday.", "Good luck to her with the move.")
        self.clock.t += 30
        a.add("Ada", "And what day is that?", "Saturday.")
        b = self.make()                                     # the proxy started again
        self.assertEqual([u for u, _ in b.recent("Ada")],
                         ["My sister moves on Saturday.", "And what day is that?"])
        self.assertEqual([x["user"] for x in b.session()],
                         ["My sister moves on Saturday.", "And what day is that?"])

    def test_the_words_come_back_as_typed_and_the_reply_as_shown(self):
        a = self.make()
        typed = "Two  spaces\\nand a line"
        long_reply = "word " * 300                           # longer than a prompt carries
        a.add("Ada", typed, long_reply)
        x = self.make().session()[0]
        self.assertEqual(x["user"], typed)
        self.assertEqual(x["reply"], long_reply.strip())
        self.assertLessEqual(len(self.make().recent("Ada")[0][1]), wm.REPLY_MAX + 4)

    def test_it_is_ram_and_one_persons(self):
        a = self.make()
        a.add("Ada", "hello", "hi")
        path = os.path.join(self.dir, wm.SESSION_FILE)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        for unit in ("aetherseed-proxy.service", "aetherseed-proxy@.service"):
            with open(os.path.join(HERE, "services", unit)) as f:
                u = f.read()
            m = re.search(r"^Environment=AETHERSEED_SESSION_DIR=(/run/aetherseed-session/\S+)$", u, re.M)
            self.assertTrue(m, unit)
            self.assertIn("TemporaryFileSystem=/run/aetherseed-session:ro", u)
            self.assertIn("BindPaths=" + m.group(1), u)
            self.assertIn("aetherseed-session/" + m.group(1).rsplit("/", 1)[1], u.split("RuntimeDirectory=")[1].split("\n")[0])

    def test_a_long_pause_ends_the_session_as_it_ends_the_prompt(self):
        a = self.make()
        a.add("Ada", "first", "one")
        self.clock.t += wm.SESSION_WINDOW_S + 1
        self.assertEqual(a.session(), [])
        self.assertEqual(a.recent("Ada"), [])

    def test_ten_minutes_ends_the_prompt_but_not_the_session(self):
        a = self.make()
        a.add("Ada", "first", "one")
        self.clock.t += wm.WINDOW_S + 1
        self.assertEqual(a.recent("Ada"), [])
        self.assertEqual(len(a.session()), 1)

    def test_forgetting_reaches_the_copy_in_run(self):
        a = self.make()
        a.add("Ada", "my code word is heron", "noted")
        a.add("Ada", "nice weather", "yes")
        a.forget(lambda text: "heron" in text)
        b = self.make()
        self.assertEqual([x["user"] for x in b.session()], ["nice weather"])
        with open(os.path.join(self.dir, wm.SESSION_FILE)) as f:
            self.assertNotIn("heron", f.read())
        a.clear()
        self.assertEqual(self.make().session(), [])

    def test_a_file_from_another_boot_or_broken_is_passed_over(self):
        with open(os.path.join(self.dir, wm.SESSION_FILE), "w") as f:
            json.dump([{"at": self.clock.t + 99999, "speaker": "Ada", "user": "future", "reply": "x"},
                       {"speaker": "Ada"}, "nonsense"], f)
        self.assertEqual(self.make().session(), [])
        with open(os.path.join(self.dir, wm.SESSION_FILE), "w") as f:
            f.write("{not json")
        self.assertEqual(self.make().session(), [])

    def test_without_a_folder_it_is_this_process_only(self):
        a = self.make(folder=False)
        a.add("Ada", "hello", "hi")
        self.assertEqual(os.listdir(self.dir), [])
        self.assertEqual(len(a.session()), 1)

    def test_the_session_is_capped(self):
        a = self.make()
        for i in range(wm.SESSION_KEEP + 15):
            a.add("Ada", "q%d" % i, "a%d" % i)
            self.clock.t += 5
        got = self.make().session()
        self.assertEqual(len(got), wm.SESSION_KEEP)
        self.assertEqual(got[-1]["user"], "q%d" % (wm.SESSION_KEEP + 14))


class MoreForARoomierModel(unittest.TestCase):
    def test_the_4b_takes_six_the_smaller_ones_three(self):
        from logic.token_budget import MODELS
        self.assertEqual(max_exchanges_for(MODELS["qwen3:4b"]["ceiling"]), 6)
        self.assertEqual(max_exchanges_for(1536), 3)
        self.assertEqual(max_exchanges_for(1056), 3)
        self.assertEqual(max_exchanges_for(None), 3)


class AtTheConsole(unittest.TestCase):
    def test_the_session_route_goes_to_the_persons_own_proxy(self):
        import sys
        sys.path.insert(0, os.path.join(HERE, "gui"))
        import serve
        self.assertIn("/aetherseed/session", serve.PROXIED_GET)
        self.assertNotIn("/aetherseed/session", serve.OPEN_GET)          # signed in only
        self.assertNotIn("/aetherseed/session", getattr(serve, "OWNER_ONLY_GET", ()))

    def test_the_page_clears_the_talk_when_the_person_changes(self):
        with open(os.path.join(HERE, "gui", "index.html"), encoding="utf-8") as f:
            page = f.read()
        # cleared, keeping only the intro note
        self.assertIn("transcript.replaceChildren(introNote)", page)
        # its words are set through handles kept from the start: looked up by
        # id after the note was taken off, the language change threw halfway
        self.assertNotIn("$('intro1')", page.split("const introNote")[1].split("\n", 1)[1])
        self.assertNotIn("$('intro2')", page.split("const introNote")[1].split("\n", 1)[1])
        self.assertIn("fetch('/aetherseed/session')", page)


if __name__ == "__main__":
    unittest.main()
