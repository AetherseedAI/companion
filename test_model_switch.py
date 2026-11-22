"""The served model can be switched: by root at a shell (tools/model.py), or
asked for by the owner at the console, which only leaves the model's name for
the unit's root side (gui/serve.py, services/aetherseed-model.*)."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "gui"))
import serve                       # noqa: E402
import signin                      # noqa: E402
from logic import model_switch as ms    # noqa: E402
from logic.token_budget import MODELS   # noqa: E402


class WhatCanBeChosen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="model-")
        self.blob = os.path.join(self.tmp, "blob"); os.makedirs(self.blob)
        self.state = os.path.join(self.tmp, "state"); os.makedirs(self.state)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def put(self, name):
        open(os.path.join(self.blob, name), "w").close()

    def test_a_model_needs_a_profile_a_measured_ceiling_its_file_and_its_tokenizer(self):
        why = lambda n: ms.why_not(n, self.blob, self.state)
        self.assertIn("not a model's name", why("../../etc/passwd"))
        self.assertIn("not a model's name", why("qwen3:4b; reboot"))
        self.assertIn("no profile", why("gpt:5"))
        self.assertIn("not in the model store", why("qwen3:4b"))
        self.put("Qwen3-4B-Instruct-2507.hef.sha256")           # the sum alone is not the file
        self.assertIn("not in the model store", why("qwen3:4b"))
        self.put("Qwen3-4B-Instruct-2507.hef")
        self.assertIn("tokenizer", why("qwen3:4b"))
        open(os.path.join(self.state, MODELS["qwen3:4b"]["tokenizer"]), "w").close()
        self.assertIsNone(why("qwen3:4b"))
        # the 1.7B's file is not the 4B's: each is looked for by its own name
        self.assertIn("not in the model store", why("qwen3:1.7b"))

    def test_every_model_offered_has_a_measured_ceiling(self):
        for name in ms.FILES:
            self.assertIsNotNone(MODELS[name].get("ceiling"), name)
        self.assertEqual(MODELS["qwen3:4b"]["tokenizer"], MODELS["qwen3:1.7b"]["tokenizer"])

    def test_the_units_own_file_decides_between_two_ceilings_of_one_name(self):
        # HailoRT 5.5.0's Qwen3-1.7B is another compile than 5.4.0's and reads
        # less (measured on a unit): the file in the store says which it is
        from logic import token_budget as tb
        fresh = lambda: {k: dict(v) for k, v in tb.MODELS.items()}
        old_bytes, new_bytes = 2880748478, 2955754430

        def store(size):
            path = os.path.join(self.blob, "Qwen3-1.7B-Instruct.hef")
            with open(path, "wb") as f:
                f.truncate(size)                       # a sparse file: its size, no bytes

        m = fresh(); m["qwen3:1.7b"]["ceiling"] = 1536
        store(old_bytes)
        self.assertEqual(tb.fit_to_store(m, self.blob), {})
        self.assertEqual(m["qwen3:1.7b"]["ceiling"], 1536)
        store(new_bytes)
        self.assertEqual(tb.fit_to_store(m, self.blob), {"qwen3:1.7b": 1056})
        self.assertEqual(m["qwen3:1.7b"]["ceiling"], 1056)
        self.assertEqual(m["qwen3:4b"]["ceiling"], 2048)            # untouched
        m = fresh(); m["qwen3:1.7b"]["ceiling"] = 1536
        self.assertEqual(tb.fit_to_store(m, os.path.join(self.tmp, "no-such-folder")), {})
        self.assertEqual(m["qwen3:1.7b"]["ceiling"], 1536)          # an unknown store: the profile's own

    def test_the_setting_is_one_whole_line(self):
        path = os.path.join(self.tmp, "model.env")
        ms.write_setting("qwen3:4b", path)
        self.assertEqual(open(path).read(), "AETHERSEED_MODEL=qwen3:4b\n")
        from logic import served
        self.assertEqual(served.configured_model(environ={}, path=path), "qwen3:4b")

    def test_the_list_for_the_console_says_what_is_ready(self):
        self.put("Qwen3-1.7B-Instruct.hef")
        open(os.path.join(self.state, MODELS["qwen3:1.7b"]["tokenizer"]), "w").close()
        path = os.path.join(self.tmp, "models.json")
        ms.write_choices(path, self.blob, self.state)
        got = {m["name"]: m["ready"] for m in json.load(open(path))["models"]}
        self.assertTrue(got["qwen3:1.7b"])
        self.assertFalse(got["qwen3:4b"])

    def test_the_tools_and_units_are_in_the_build(self):
        mode = subprocess.run(["git", "ls-files", "-s", "tools/model.py"], cwd=HERE,
                              capture_output=True, text=True).stdout.split(" ")[0]
        if mode:
            self.assertEqual(mode, "100755")
        with open(os.path.join(HERE, "install.sh"), encoding="utf-8") as f:
            inst = f.read()
        for u in ("aetherseed-model.path", "aetherseed-model.service"):
            self.assertTrue(os.path.exists(os.path.join(HERE, "services", u)), u)
            self.assertIn(u, inst)
        self.assertIn('tools/model.py" choices', inst)
        with open(os.path.join(HERE, "services", "aetherseed-model.path")) as f:
            self.assertIn("PathExists=/run/aetherseed-gui/model-request", f.read())


class _Quiet(serve.Console):
    def log_message(self, *a):
        pass


class AtTheConsole(unittest.TestCase):
    """The console offers what root listed, files a name, and nothing more."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="modelc-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.keep = {k: getattr(serve, k) for k in
                     ("MODEL_REQUEST", "MODEL_RESULT", "MODEL_CHOICES", "MODEL_FILE")}
        for k in self.keep:
            setattr(serve, k, os.path.join(self.tmp, k.lower()))
        self.addCleanup(lambda: [setattr(serve, k, v) for k, v in self.keep.items()])
        with open(serve.MODEL_CHOICES, "w") as f:
            json.dump({"models": [{"name": "qwen3:1.7b", "ready": True, "why_not": None},
                                  {"name": "qwen3:4b", "ready": True, "why_not": None},
                                  {"name": "llama3.2:1b", "ready": False, "why_not": "no file"},
                                  {"name": "x; rm -rf /", "ready": True, "why_not": None}]}, f)
        with open(serve.MODEL_FILE, "w") as f:
            f.write("AETHERSEED_MODEL=qwen3:1.7b\n")
        self.who = signin.OWNER
        test = self
        class H(_Quiet):
            def _who(self):
                return test.who
            def _refused_if_not_from_here(self):
                return False
        self.srv = serve.Threaded(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def req(self, method, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        data = None if body is None else json.dumps(body).encode()
        c.request(method, serve.MODEL_PATH, data,
                  {"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.srv.server_address[1],
                   "Host": "127.0.0.1:%d" % self.srv.server_address[1]} if data is not None else {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, (json.loads(raw) if raw else {})

    def test_the_owner_sees_the_model_and_the_choices(self):
        code, d = self.req("GET")
        self.assertEqual(code, 200)
        self.assertEqual(d["model"], "qwen3:1.7b")
        self.assertEqual([m["name"] for m in d["models"]], ["qwen3:1.7b", "qwen3:4b", "llama3.2:1b"])
        self.assertFalse(d["switching"])

    def test_asking_leaves_the_name_and_nothing_else(self):
        code, d = self.req("POST", {"model": "qwen3:4b", "extra": "ignored"})
        self.assertEqual(code, 202, d)
        self.assertEqual(open(serve.MODEL_REQUEST).read(), "qwen3:4b\n")
        self.assertEqual(open(serve.MODEL_FILE).read(), "AETHERSEED_MODEL=qwen3:1.7b\n")   # the console changed nothing
        self.assertEqual(self.req("POST", {"model": "qwen3:4b"})[0], 409)                   # one switch at a time
        self.assertTrue(self.req("GET")[1]["switching"])

    def test_a_name_root_did_not_list_as_ready_is_refused(self):
        for name in ("llama3.2:1b", "x; rm -rf /", "gpt:5", "", None, 7, ["qwen3:4b"]):
            code, d = self.req("POST", {"model": name})
            self.assertEqual(code, 400, name)
            self.assertFalse(os.path.exists(serve.MODEL_REQUEST), name)

    def test_the_model_already_served_is_not_a_switch(self):
        self.assertEqual(self.req("POST", {"model": "qwen3:1.7b"})[0], 200)
        self.assertFalse(os.path.exists(serve.MODEL_REQUEST))

    def test_only_the_owner(self):
        self.who = {"id": "mira", "name": "Mira"}          # a person the owner added
        self.assertEqual(self.req("GET")[0], 403)
        self.assertEqual(self.req("POST", {"model": "qwen3:4b"})[0], 403)
        self.who = None                                    # not signed in
        self.assertEqual(self.req("GET")[0], 401)
        self.assertEqual(self.req("POST", {"model": "qwen3:4b"})[0], 401)
        self.assertFalse(os.path.exists(serve.MODEL_REQUEST))

    def test_the_outcome_root_left_is_shown(self):
        with open(serve.MODEL_RESULT, "w") as f:
            json.dump({"ok": True, "asked": "qwen3:4b", "message": "This unit now serves qwen3:4b."}, f)
        self.assertEqual(self.req("GET")[1]["last"]["asked"], "qwen3:4b")


class TheInstaller(unittest.TestCase):

    def test_it_restarts_what_serves_a_changed_model(self):
        # A unit, 14 Nov 2026: the keep-alive kept the old model after
        # install.sh --model, and the chip swapped models under every talk
        with open(os.path.join(HERE, "install.sh"), encoding="utf-8") as f:
            sh = f.read()
        self.assertIn('WAS_MODEL=$MODEL', sh)
        self.assertIn('systemctl restart hailo-ollama', sh)

    def test_nothing_is_loading_when_the_server_restarts(self):
        # A unit, 16 Nov 2026: the server was restarted while the warm-up's load
        # of the new model ran; the chip answered "LLM not loaded" until a
        # reboot. What asks for a model stops first; the server restarts; the
        # rest starts after it.
        with open(os.path.join(HERE, "install.sh"), encoding="utf-8") as f:
            sh = f.read()
        stop = sh.index('systemctl stop aetherseed-keepalive aetherseed-warmup aetherseed-proxy')
        restart = sh.index('systemctl restart hailo-ollama')
        start = sh.index('systemctl enable --now $UNITS')
        self.assertLess(stop, restart)
        self.assertLess(restart, start)
        self.assertNotIn('systemctl restart hailo-ollama aetherseed-keepalive', sh)
        self.assertIn('systemctl start $PEOPLE_UP', sh)



if __name__ == "__main__":
    unittest.main()
