"""Errands through the proxy: a turn with "aetherseed_errand", the approval queue
carrying out what was filed, and the console's routes (28 Nov 2026).

A stand-in Claude (no key, no network) and the scripted hailo-ollama of
test_memory_turn. What is checked is the unit's side of it.
"""
import http.client
import json
import os
import unittest

import proxy                            # first, and for real (see test_brake)
from test_memory_turn import SCRIPT, _Proxy
from logic.connectors import Email
from logic import errands as errands_mod


class FakeCloud:
    def __init__(self, script):
        self.script, self.asked, self.streamed = list(script), [], []

    def ready(self):
        return True

    def status(self):
        return {"on": True, "switched_on": True, "key": True, "key_end": "TEST",
                "model": "claude-sonnet-5-5", "models": ["claude-sonnet-5-5"]}

    def ask(self, system, turns, tools, max_tokens=0):
        self.asked.append({"system": system, "turns": turns, "tools": [t["name"] for t in tools]})
        return self.script.pop(0) if self.script else {
            "content": [{"type": "text", "text": "(done)"}], "stop_reason": "end_turn"}

    def stream(self, messages, on_text, writing=False):
        self.streamed.append(messages)
        on_text("Plain Claude answer.")
        return "Plain Claude answer."


def use(name, args):
    return {"content": [{"type": "tool_use", "id": "t1", "name": name, "input": args}],
            "stop_reason": "tool_use"}


def say(text):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


class ErrandTurns(_Proxy):
    def setUp(self):
        super().setUp()
        self._cloud = proxy.CLOUD
        proxy._ERRANDS.clear()
        self.sent = []

    def tearDown(self):
        proxy.CLOUD = self._cloud
        proxy._ERRANDS.clear()
        super().tearDown()

    def claude(self, *script):
        proxy.CLOUD = FakeCloud(script)
        proxy._ERRANDS.clear()
        e = proxy.errands_engine()
        sent = self.sent

        class SMTP:
            def login(self, u, p): pass
            def send_message(self, m): sent.append(m)
            def quit(self): pass
        e.connectors["email"] = Email(e.settings, imap=lambda c: None, smtp=lambda c: SMTP())
        e.settings.set_config("email", {"on": True, "address": "sam@example.no", "imap_host": "imap.example.no",
                                        "smtp_host": "smtp.example.no", "smtp_port": 465})
        e.settings.set_secret("email_password", "synthetic-not-real")
        return e

    def post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=30)
        c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"{}"))
        c.close()
        return out

    def errand(self, text, **extra):
        body = {"model": "llama3.2:3b", "stream": True, "aetherseed_errand": True,
                "messages": [{"role": "user", "content": text}], **extra}
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=30)
        c.request("POST", "/api/chat", body=json.dumps(body), headers={"Content-Type": "application/json"})
        r = c.getresponse()
        lines = [json.loads(l) for l in r.read().decode().split("\n") if l.strip()]
        c.close()
        meta = next((l["aetherseed"] for l in lines if l.get("done")), None)
        return "".join((l.get("message") or {}).get("content", "") for l in lines), meta

    def test_an_email_errand_is_filed_said_as_waiting_and_sent_only_on_a_yes(self):
        self.claude(use("email_send", {"to": "christian@example.no", "subject": "Saturday", "body": "19 works."}),
                    say("I have written it; it is waiting for your yes."))
        text, meta = self.errand("Email Christian that 19 on Saturday works")
        self.assertIn("I have written it", text)
        self.assertIn("Waiting for your yes in the console: an email to christian@example.no", text)
        self.assertEqual(meta["brain"], "claude")
        self.assertEqual(meta["errand"]["waiting"], 1)
        self.assertEqual(self.sent, [])
        pending = self.get("/aetherseed/approvals")["pending"]
        self.assertEqual(pending[0]["tool"], errands_mod.TOOL_PREFIX + "email_send")
        status, d = self.post("/aetherseed/approvals", {"id": pending[0]["id"], "action": "approve",
                                                        "reason": "yes, send it"})
        self.assertEqual(status, 200)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["Subject"], "Saturday")

    def test_the_errand_gets_the_turns_own_prompt_and_only_the_switched_on_tools(self):
        e = self.claude(say("Nothing to do."))
        e.settings.set_config("lists", {"on": True})
        self.errand("What is on the shopping list?")
        asked = proxy.CLOUD.asked[0]
        self.assertEqual(set(asked["tools"]), {"email_search", "email_read", "email_send",
                                               "list_read", "list_add", "list_remove"})
        self.assertIn(errands_mod.RULES[:40], asked["system"])
        self.assertEqual(asked["turns"][-1]["content"], "What is on the shopping list?")

    def test_a_vault_turn_is_never_an_errand(self):
        self.claude(say("should not be asked"))
        text, meta = self.errand("my private thing", aetherseed_vault=True)
        self.assertEqual(proxy.CLOUD.asked, [])
        self.assertNotEqual(meta.get("brain"), "claude")
        self.assertTrue(meta.get("vault"))

    def test_without_the_flag_a_turn_is_an_ordinary_claude_turn(self):
        self.claude(say("x"))
        status, text, meta = self.ask("hello")
        self.assertEqual(proxy.CLOUD.asked, [])
        self.assertEqual(text, "Plain Claude answer.")
        self.assertNotIn("errand", meta)


class TheRoutes(ErrandTurns):
    def test_the_view_shows_what_is_set_never_the_secrets(self):
        self.claude()
        view = self.get("/aetherseed/errands")
        names = {c["name"]: c for c in view["connectors"]}
        self.assertEqual(set(names), {"web", "calendar", "email", "lists"})
        self.assertTrue(names["email"]["on"])
        self.assertEqual(names["email"]["secrets"], {"email_password": True})
        self.assertNotIn("synthetic-not-real", json.dumps(view))
        self.assertIn("errands", self.get("/aetherseed/status"))

    def test_switch_settings_and_secrets(self):
        self.claude()
        st, d = self.post("/aetherseed/errands", {"action": "switch", "name": "web", "on": True})
        self.assertEqual(st, 200)
        self.assertTrue(next(c for c in d["connectors"] if c["name"] == "web")["on"])
        st, d = self.post("/aetherseed/errands", {"action": "settings", "name": "email",
                                                  "settings": {"imap_port": "70000"}})
        self.assertEqual((st, d.get("code")), (400, "bad_port"))
        st, d = self.post("/aetherseed/errands", {"action": "secret", "name": "calendar_url",
                                                  "value": "http://insecure.example/cal.ics"})
        self.assertEqual((st, d.get("code")), (400, "calendar_url_https_only"))
        st, d = self.post("/aetherseed/errands", {"action": "secret", "name": "calendar_url",
                                                  "value": "https://cal.example/private-abc.ics"})
        self.assertEqual(st, 200)
        self.assertTrue(next(c for c in d["connectors"] if c["name"] == "calendar")["secrets"]["calendar_url"])
        self.assertNotIn("private-abc", json.dumps(d))
        for bad in ({"action": "switch", "name": "shell"}, {"action": "secret", "name": "anthropic_key"},
                    {"action": "nope"}):
            self.assertEqual(self.post("/aetherseed/errands", bad)[0], 400, bad)


if __name__ == "__main__":
    unittest.main()
