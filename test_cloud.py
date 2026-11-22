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
