"""Claude with the owner's own key, and the vault (logic/cloud.py, 21 Nov 2026).

    python3 -m unittest test_cloud -v

No network: the opener is a stand-in that records the request and plays back
a stream of server-sent events.
"""
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from logic import cloud as cloud_mod          # noqa: E402
from logic.journal import Journal             # noqa: E402

KEY = "sk-ant-api03-" + "x" * 40


def sse(*texts, error=None):
    out = [b'event: message_start\n', b'data: {"type":"message_start"}\n', b'\n']
    for t in texts:
        out.append(b"data: " + json.dumps({"type": "content_block_delta", "index": 0,
                                           "delta": {"type": "text_delta", "text": t}}).encode() + b"\n")
    if error:
        out.append(b"data: " + json.dumps({"type": "error", "error": {"type": error}}).encode() + b"\n")
    out.append(b'data: {"type":"message_stop"}\n')
    return out


class Opener:
    def __init__(self, lines=None, raise_=None):
        self.lines, self.raise_, self.req = lines or [], raise_, None

    def __call__(self, req, timeout):
        self.req = req
        if self.raise_:
            raise self.raise_
        return io.BytesIO(b"".join(self.lines))


class TheKeyAndTheSwitch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.c = cloud_mod.Cloud(self.dir)

    def test_off_until_a_key_is_set_and_it_is_switched_on(self):
        self.assertFalse(self.c.ready())
        self.c.switch(on=True)
        self.assertFalse(self.c.ready(), "no key: not on")
        self.c.set_key(KEY)
        self.assertTrue(self.c.ready())

    def test_the_key_is_readable_by_its_owner_only_and_never_shown(self):
        self.c.set_key(KEY)
        mode = stat.S_IMODE(os.stat(os.path.join(self.dir, cloud_mod.KEY_FILE)).st_mode)
        self.assertEqual(mode, 0o600)
        st = self.c.status()
        self.assertNotIn(KEY, json.dumps(st))
        self.assertEqual(st["key_end"], KEY[-4:])

    def test_what_is_not_a_key_is_refused(self):
        for bad in ("", "hello", "sk-ant-short", "sk-ant-" + "x" * 20 + " y", "sk-" + "x" * 40):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.c.set_key(bad)

    def test_forgetting_the_key_switches_claude_off(self):
        self.c.set_key(KEY); self.c.switch(on=True)
        self.c.forget_key()
        self.assertFalse(self.c.status()["key"])
        self.assertFalse(self.c.status()["switched_on"])

    def test_only_the_offered_models(self):
        with self.assertRaises(ValueError):
            self.c.switch(model="gpt-5")
        self.c.switch(model="claude-haiku-5-5")
        self.assertEqual(self.c.status()["model"], "claude-haiku-5-5")


class OneAnswer(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.op = Opener(sse("Hei", ", Aria."))
        self.c = cloud_mod.Cloud(self.dir, opener=self.op)
        self.c.set_key(KEY); self.c.switch(on=True)

    def test_it_streams_and_asks_anthropic_only(self):
        got = []
        text = self.c.stream([{"role": "system", "content": "charter"},
                              {"role": "user", "content": "hei"}], got.append)
        self.assertEqual(text, "Hei, Aria.")
        self.assertEqual(got, ["Hei", ", Aria."])
        self.assertEqual(self.op.req.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(self.op.req.get_header("X-api-key"), KEY)
        body = json.loads(self.op.req.data)
        self.assertEqual(body["system"], "charter")
        self.assertEqual(body["messages"], [{"role": "user", "content": "hei"}])
        self.assertEqual(body["max_tokens"], cloud_mod.MAX_TOKENS)
        self.assertTrue(body["stream"])

    def test_writing_asks_for_more(self):
        self.c.stream([{"role": "user", "content": "skriv"}], lambda _: None, writing=True)
        self.assertEqual(json.loads(self.op.req.data)["max_tokens"], cloud_mod.MAX_TOKENS_WRITING)

    def test_turns_are_made_to_alternate_and_begin_with_the_person(self):
        system, turns = cloud_mod.Cloud.as_request([
            {"role": "assistant", "content": "stray"},
            {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"}, {"role": "user", "content": "d"}])
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user"])
        self.assertEqual(turns[0]["content"], "a\n\nb")

    def test_every_failure_is_a_cloud_error(self):
        for op in (Opener(raise_=urllib.error.HTTPError("u", 401, "no", {}, None)),
                   Opener(raise_=OSError("no route")),
                   Opener(sse()),                      # nothing said
                   Opener(sse(error="overloaded_error"))):
            with self.subTest(op=op.raise_ or "stream"):
                c = cloud_mod.Cloud(self.dir, opener=op)
                with self.assertRaises(cloud_mod.CloudError):
                    c.stream([{"role": "user", "content": "x"}], lambda _: None)

    def test_switched_off_nothing_is_sent(self):
        self.c.switch(on=False)
        with self.assertRaises(cloud_mod.CloudError):
            self.c.stream([{"role": "user", "content": "x"}], lambda _: None)
        self.assertIsNone(self.op.req)


class TheVault(unittest.TestCase):
    """A vaulted entry is in the journal, private; the journal's recent()
    leaves it out when asked to - which is what a cloud turn asks."""

    def test_private_entries_stay_out_of_what_goes(self):
        d = tempfile.mkdtemp()
        jr = Journal(d)
        jr.append("steward", "the dog is called Tass")
        jr.append("steward", "the surprise party is on Friday", private=True)
        said = [e["said"] for e in jr.recent(exclude_private=True)]
        self.assertEqual(said, ["the dog is called Tass"])
        self.assertEqual(len(jr.recent()), 2, "at home, everything is still hers")
        text = open(os.path.join(d, "journal.md")).read()
        self.assertIn("private", text)


if __name__ == "__main__":
    unittest.main()


class WhatSheSaysAboutTheCloud(unittest.TestCase):
    """While Claude is on, "nothing leaves this device" is not true: the unit
    says what is, and Claude's prompt carries the same line in its place."""

    def test_the_line_replaced_is_the_shipped_one(self):
        from logic.knowledge import load_knowledge
        k = load_knowledge()
        self.assertEqual(k.by_id("self.local"), cloud_mod.LOCAL_LINE)

    def test_the_line_said_while_claude_is_on_names_the_vault_and_what_stays(self):
        line = cloud_mod.CLAUDE_ON_LINE
        for word in ("Anthropic", "Vault", "this device"):
            self.assertIn(word, line)
        self.assertNotIn("Nothing said to me leaves", line)


class ClaudesOwnSizes(unittest.TestCase):
    """Until 25 Nov 2026 Claude was handed the prompt cut for the chip: some
    1,900 characters of memory, six exchanges cut to 400 characters each,
    5,000 characters of a file, and 1,024 tokens to answer in. A turn Claude
    answers has its own sizes (cloud_mod.LIMITS), which the owner can set in
    cloud.json; the local model's are untouched."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.op = Opener(sse("Hei"))
        self.c = cloud_mod.Cloud(self.dir, opener=self.op)
        self.c.set_key(KEY); self.c.switch(on=True)

    def _own(self, limits):
        with open(os.path.join(self.dir, cloud_mod.CONFIG_FILE)) as f:
            c = json.load(f)
        c["limits"] = limits
        with open(os.path.join(self.dir, cloud_mod.CONFIG_FILE), "w") as f:
            json.dump(c, f)

    def test_the_defaults_are_not_the_chips(self):
        lim = self.c.limits()
        self.assertEqual(lim, cloud_mod.LIMITS)
        self.assertGreaterEqual(lim["memory_chars"], 20000)
        self.assertGreaterEqual(lim["exchanges"], 40)
        self.assertEqual(self.c.status()["limits"], lim)

    def test_the_owner_sets_them_and_nonsense_is_passed_over(self):
        self._own({"memory_chars": 6000, "max_tokens": 2000, "exchanges": 0,
                   "timeout_s": "long", "file_chars": True, "unknown": 5})
        lim = self.c.limits()
        self.assertEqual((lim["memory_chars"], lim["max_tokens"]), (6000, 2000))
        for k in ("exchanges", "timeout_s", "file_chars"):
            self.assertEqual(lim[k], cloud_mod.LIMITS[k])
        self.assertNotIn("unknown", lim)
        self.c.switch(model="claude-haiku-5-5")          # the switch keeps them
        self.assertEqual(self.c.limits()["memory_chars"], 6000)

    def test_the_answer_and_the_wait_follow_them(self):
        seen = {}
        def op(req, timeout):
            seen["timeout"] = timeout
            return self.op(req, timeout)
        self.c._open = op
        self._own({"max_tokens": 3000, "max_tokens_writing": 9000, "timeout_s": 120})
        self.c.stream([{"role": "user", "content": "hei"}], lambda _: None)
        self.assertEqual(json.loads(self.op.req.data)["max_tokens"], 3000)
        self.assertEqual(seen["timeout"], 120)
        self.c.stream([{"role": "user", "content": "skriv"}], lambda _: None, writing=True)
        self.assertEqual(json.loads(self.op.req.data)["max_tokens"], 9000)

    def test_the_conversation_as_it_was_said(self):
        from logic.working_memory import WorkingMemory, REPLY_MAX
        now = [1000.0]
        wm = WorkingMemory(max_exchanges=3, clock=lambda: now[0])
        long_reply = "word " * 300
        for i in range(10):
            wm.add("sam", "question %d" % i, long_reply)
            now[0] += 60
        chip = wm.recent("sam")
        self.assertEqual(len(chip), 3)
        self.assertLessEqual(len(chip[0][1]), REPLY_MAX + 4)
        claude = wm.recent("sam", limit=40, window_s=7200, full=True)
        self.assertEqual([u for u, _ in claude], ["question %d" % i for i in range(10)])
        self.assertEqual(claude[0][1], long_reply.strip())
        now[0] += 1800                       # half an hour later
        self.assertEqual(wm.recent("sam"), [])
        self.assertEqual(len(wm.recent("sam", limit=40, window_s=7200, full=True)), 10)

    def test_a_file_read_follows_the_turn(self):
        import intent_detection
        self.assertEqual(intent_detection.READ_CHARS, 5000)
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py"),
                   encoding="utf-8").read()
        self.assertIn('CLOUD.limits()["file_chars"] if cloud_now()', src)

    def test_claude_is_sent_the_prompt_as_built(self):
        # the handler asks Claude before the fit to the chip's ceiling, and
        # fits only when the local model is the one answering
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py"),
                   encoding="utf-8").read()
        h = src[src.index("    def _proxy_chat_augmented"):]
        ask = h.index("answered = call_cloud(model, messages, stream)")
        fit = h.index("messages, budget = enforce_budget(token_counter(model), messages)")
        self.assertLess(ask, fit)
        self.assertIn("if answered is None:\n                messages, budget = enforce_budget", h)
        self.assertIn('max_chars=lim["memory_chars"]', h)
        self.assertIn('max_retrieved=lim["memory_turns"]', h)
        c = src[src.index("def call_cloud"):src.index("def _cloud_reply")]
        self.assertIn("_MODEL_LOCK", c)
        self.assertIn("BRAKE.is_set()", c)


class MemoryForClaude(unittest.TestCase):
    def test_the_block_is_the_turns_size_when_it_brings_one(self):
        import shutil
        import aetherroot
        tmp = tempfile.mkdtemp(prefix="cloudmem-")
        d = os.path.join(tmp, "aetherroot"); os.makedirs(d)
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump(dict(aetherroot.DEFAULT_CONFIG), f)
        root = aetherroot.AetherRoot(d)
        try:
            for i in range(30):
                root.store_interaction(
                    "The greenhouse log for bed %d: tomatoes planted in row %d." % (i, i),
                    "Noted, bed %d has tomatoes in row %d, and I will remember it." % (i, i))
            q = "What does the greenhouse log say about the tomatoes?"
            chip, claude = {}, {}
            a = root.retrieve_context(q, report=chip)
            b = root.retrieve_context(q, report=claude, max_chars=24000, max_retrieved=40)
            self.assertLessEqual(len(a), root.config["max_context_chars"] + 200)
            self.assertGreater(len(b), len(a) * 2)
            self.assertGreater(b.count("\n- "), a.count("\n- "))
            self.assertEqual(root.config["max_context_chars"],
                             aetherroot.DEFAULT_CONFIG["max_context_chars"])
        finally:
            root.close(); shutil.rmtree(tmp, ignore_errors=True)
