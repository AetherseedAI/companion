"""More than one person on a unit, a root each (gui/people.py, gui/serve.py).

What is held here: a member's requests reach that member's own proxy and no
other; the owner's reach the owner's; what is the unit's stays the owner's;
the first sign-in under a name sets its passkey, once. Every name is made
for the test."""
import http.client
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "gui"))
import signin  # noqa: E402
import people  # noqa: E402
import serve  # noqa: E402

OWNER_KEY = "owner-passkey-1"
MIRA_KEY = "mira picks this one"
FAST = 10_000


def _recorder(steward):
    """A stand-in proxy that remembers what reached it."""
    class H(http.server.BaseHTTPRequestHandler):
        seen = []

        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            H.seen.append(("GET", self.path, None))
            if self.path == "/aetherseed/status":
                self._send({"companion": {"configured": True, "name": "Aria", "steward": steward}})
            else:
                self._send({"whose": steward})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            H.seen.append(("POST", self.path, self.rfile.read(n)))
            self._send({"whose": steward, "message": {"content": "hi"}, "done": True})
    return H


class ThePeopleFile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="people-")
        self.file = os.path.join(self.tmp, "people.json")
        self.keys = os.path.join(self.tmp, "keys")
        os.mkdir(self.keys)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_an_id_is_plain_and_never_the_owners(self):
        self.assertEqual(people.make_id("Åse-Marie", set()), "asemarie")
        self.assertEqual(people.make_id("Mira", {"mira"}), "mira2")
        self.assertEqual(people.make_id("Ow Ner", set()), "owner2")      # "owner" is the owner's
        self.assertEqual(people.make_id("123", set()), "p123")
        self.assertTrue(people.valid_id(people.make_id("李", set())))

    def test_a_file_that_is_not_this_shape_is_no_members(self):
        self.assertEqual(people.load(self.file), [])                      # missing
        for bad in ("not json", "[]", '{"people": "x"}'):
            with open(self.file, "w") as f:
                f.write(bad)
            self.assertEqual(people.load(self.file), [])
        with open(self.file, "w") as f:
            json.dump({"people": [{"id": "mira", "name": "Mira", "port": 8011},
                                  {"id": "../x", "name": "Bad", "port": 8012},      # not an id
                                  {"id": "mira", "name": "Twin", "port": 8013},     # the same id
                                  {"id": "tor", "name": "mira", "port": 8014},      # the same name
                                  {"id": "una", "name": "Una", "port": 8011},       # the same port
                                  {"id": "low", "name": "Low", "port": 80}]}, f)
        self.assertEqual(people.load(self.file), [{"id": "mira", "name": "Mira", "port": 8011}])

    def test_the_first_claim_wins_and_only_the_hash_is_kept(self):
        self.assertFalse(people.has_key("mira", self.keys))
        self.assertEqual(people.claim("mira", "short", self.keys), "bad_passkey")
        self.assertFalse(people.has_key("mira", self.keys))
        self.assertEqual(people.claim("mira", MIRA_KEY, self.keys), "claimed")
        self.assertEqual(people.claim("mira", "somebody else's", self.keys), "taken")
        self.assertTrue(people.check("mira", MIRA_KEY, self.keys))
        self.assertFalse(people.check("mira", "somebody else's", self.keys))
        with open(people.key_path("mira", self.keys)) as f:
            self.assertNotIn(MIRA_KEY, f.read())
        self.assertEqual(os.stat(people.key_path("mira", self.keys)).st_mode & 0o777, 0o600)

    def test_a_reset_makes_it_a_first_time_again(self):
        people.claim("mira", MIRA_KEY, self.keys)
        self.assertTrue(people.reset("mira", self.keys))
        self.assertFalse(people.reset("mira", self.keys))
        self.assertEqual(people.claim("mira", "a new one, hers", self.keys), "claimed")
        self.assertFalse(people.check("mira", MIRA_KEY, self.keys))

    def test_an_id_cannot_leave_the_keys_folder(self):
        for bad in ("../steward", "a/b", "", "UPPER", None):
            with self.assertRaises(ValueError):
                people.key_path(bad, self.keys)

    def test_a_name_that_already_means_somebody_is_refused(self):
        have = [{"id": "mira", "name": "Mira", "port": 8011}]
        self.assertIsNone(people.name_error("Tor", have, "Samuel", "Aria"))
        self.assertEqual(people.name_error("mira", have, "Samuel", "Aria"), "in_use")
        self.assertEqual(people.name_error("SAMUEL", have, "Samuel", "Aria"), "in_use")
        self.assertEqual(people.name_error("Aria", have, "Samuel", "Aria"), "in_use")
        self.assertEqual(people.name_error("Guest", have, "Samuel", "Aria"), "reserved")
        self.assertEqual(people.name_error("a:b", have, "Samuel", "Aria"), "characters")
        new = people.add(have, "  Tor  ")
        self.assertEqual(new, {"id": "tor", "name": "Tor", "port": 8012})


class _Unit(unittest.TestCase):
    """A console before two stand-in proxies: the owner's and one member's.
    OWN_SCREEN is emptied, so the test's connections are a phone's."""

    @classmethod
    def setUpClass(cls):
        cls.Owner, cls.Mira = _recorder("Samuel"), _recorder("Mira")
        cls.b_owner = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cls.Owner)
        cls.b_mira = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cls.Mira)
        for b in (cls.b_owner, cls.b_mira):
            threading.Thread(target=b.serve_forever, daemon=True).start()
        cls.saved = {k: getattr(serve, k) for k in
                     ("BACKEND", "OWN_SCREEN", "STEWARD_KEY", "SESSIONS", "LOCKOUT", "SHUTDOWN_REQUEST")}
        cls.saved_people = (people.PEOPLE_FILE, people.KEYS_DIR)
        serve.BACKEND = "http://127.0.0.1:%d" % cls.b_owner.server_address[1]
        cls.srv = serve.Threaded(("127.0.0.1", 0), serve.Console)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for s in (cls.srv, cls.b_owner, cls.b_mira):
            s.shutdown(); s.server_close()
        for k, v in cls.saved.items():
            setattr(serve, k, v)
        people.PEOPLE_FILE, people.KEYS_DIR = cls.saved_people

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="unit-")
        serve.OWN_SCREEN = frozenset()
        serve.STEWARD_KEY = os.path.join(self.tmp, "steward.key")
        with open(serve.STEWARD_KEY, "w") as f:
            json.dump(signin.make_record(OWNER_KEY, "own", iterations=FAST), f)
        serve.SESSIONS, serve.LOCKOUT = signin.Sessions(), signin.Lockout()
        serve.SHUTDOWN_REQUEST = os.path.join(self.tmp, "shutdown-request")
        people.PEOPLE_FILE = os.path.join(self.tmp, "people.json")
        people.KEYS_DIR = os.path.join(self.tmp, "keys")
        os.mkdir(people.KEYS_DIR)
        people.save([{"id": "mira", "name": "Mira", "port": self.b_mira.server_address[1]}])
        self.Owner.seen[:] = []
        self.Mira.seen[:] = []
        self.cookie = None

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def req(self, method, path, body=None, cookie=True):
        h = {"Content-Type": "application/json"}
        if cookie and self.cookie:
            h["Cookie"] = self.cookie
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            parsed = json.loads(data)
        except ValueError:
            parsed = None
        if r.status == 200 and r.getheader("Set-Cookie") and "=" in r.getheader("Set-Cookie"):
            got = r.getheader("Set-Cookie").split(";", 1)[0]
            self.cookie = got if got.split("=", 1)[1] else None
        return r.status, parsed

    def paths(self, backend):
        return [p.split("?", 1)[0] for _, p, _ in backend.seen]

    def as_mira(self):
        self.assertEqual(self.req("POST", serve.CLAIM_PATH, {"name": "Mira", "passkey": MIRA_KEY})[0], 200)

    def as_owner(self):
        self.assertEqual(self.req("POST", serve.SIGNIN_PATH,
                                  {"name": "Samuel", "passkey": OWNER_KEY})[0], 200)


class TheFirstSignInSetsThePasskey(_Unit):

    def test_the_page_is_told_who_is_here_and_who_is_new(self):
        d = self.req("GET", serve.WHOAMI_PATH)[1]
        self.assertEqual(d["people"], [{"name": "Mira", "first_time": True}])
        self.assertIsNone(d["person"])
        self.assertNotIn("mira", json.dumps(d))                # no ids, no ports

    def test_the_owners_name_is_told_only_where_people_were_added(self):
        full = {"companion": {"configured": True, "name": "Wren", "language": "en", "steward": "Samuel"},
                "episodes": 7}
        self.assertEqual(serve.status_before_sign_in(full, owner=True)["companion"]["steward"], "Samuel")
        self.assertNotIn("Samuel", json.dumps(serve.status_before_sign_in(full)))
        self.assertNotIn("episodes", serve.status_before_sign_in(full, owner=True))
        # through the console: told here, where Mira was added - and not once nobody is
        d = self.req("GET", "/aetherseed/status")[1]
        self.assertEqual(set(d), {"companion"})
        self.assertEqual(d["companion"].get("steward"), "Samuel")
        people.save([])
        self.assertNotIn("steward", self.req("GET", "/aetherseed/status")[1].get("companion", {}))

    def test_signing_in_before_a_passkey_exists_says_first_time(self):
        status, d = self.req("POST", serve.SIGNIN_PATH, {"name": "mira", "passkey": "anything at all"})
        self.assertEqual((status, d["code"]), (409, "first_time"))
        self.assertIsNone(self.cookie)

    def test_the_claim_signs_her_in_and_a_second_claim_is_refused(self):
        self.as_mira()
        d = self.req("GET", serve.WHOAMI_PATH)[1]
        self.assertEqual(d["person"], {"role": "member", "name": "Mira"})
        self.assertEqual(d["people"], [{"name": "Mira", "first_time": False}])
        self.cookie = None
        status, d = self.req("POST", serve.CLAIM_PATH, {"name": "Mira", "passkey": "an intruder's key"})
        self.assertEqual((status, d["code"]), (409, "taken"))
        self.assertIsNone(self.cookie)
        self.assertEqual(self.req("POST", serve.SIGNIN_PATH, {"name": "Mira", "passkey": MIRA_KEY})[0], 200)

    def test_a_wrong_passkey_is_refused_and_counted(self):
        people.claim("mira", MIRA_KEY)
        for _ in range(signin.TRIES_PER_ADDRESS):
            self.assertEqual(self.req("POST", serve.SIGNIN_PATH,
                                      {"name": "Mira", "passkey": "not hers at all"})[0], 401)
        self.assertEqual(self.req("POST", serve.SIGNIN_PATH, {"name": "Mira", "passkey": MIRA_KEY})[0], 429)

    def test_a_name_nobody_added_cannot_be_claimed(self):
        status, d = self.req("POST", serve.CLAIM_PATH, {"name": "Nobody", "passkey": MIRA_KEY})
        self.assertEqual((status, d["code"]), (404, "no_such"))
        self.assertEqual(os.listdir(people.KEYS_DIR), [])

    def test_the_owners_name_is_not_a_members(self):
        status, d = self.req("POST", serve.CLAIM_PATH, {"name": "Samuel", "passkey": MIRA_KEY})
        self.assertEqual(status, 404)


class EachPersonReachesOnlyTheirOwnRoot(_Unit):

    READS = ("/aetherseed/memories", "/aetherseed/record", "/aetherseed/rings", "/aetherseed/shelf",
             "/aetherseed/trust-record", "/aetherseed/workspace", "/aetherseed/approvals",
             "/aetherseed/status")

    def test_a_members_reads_and_turns_go_to_her_proxy_and_no_other(self):
        self.as_mira()
        self.Owner.seen[:] = []
        for path in self.READS:
            status, d = self.req("GET", path)
            self.assertEqual(status, 200, path)
        self.assertEqual(self.req("POST", "/api/chat",
                                  {"messages": [{"role": "user", "content": "Hi"}]})[1]["whose"], "Mira")
        self.assertEqual(self.req("POST", "/aetherseed/steward", {"fact": "x"})[0], 200)
        self.assertEqual(self.paths(self.Owner), [])                         # nothing reached the owner's
        self.assertEqual(set(self.paths(self.Mira)), set(self.READS) | {"/api/chat", "/aetherseed/steward"})

    def test_the_owners_go_to_the_owners(self):
        self.as_owner()
        self.Owner.seen[:] = []
        for path in self.READS:
            self.assertEqual(self.req("GET", path)[0], 200, path)
        self.assertEqual(self.paths(self.Mira), [])
        self.assertEqual(set(self.paths(self.Owner)), set(self.READS))
        self.assertEqual(self.req("GET", serve.WHOAMI_PATH)[1]["person"], {"role": "owner"})

    def test_not_signed_in_nobody_talks_and_no_root_is_reached(self):
        self.assertEqual(self.req("GET", "/aetherseed/memories")[0], 401)
        status, d = self.req("POST", "/api/chat", {"messages": [{"role": "user", "content": "Hi"}]})
        self.assertEqual((status, d), (401, {"error": "Sign in to talk with me.", "code": "sign_in"}))
        self.assertEqual(self.paths(self.Mira) + self.paths(self.Owner), [])
        d = self.req("GET", serve.WHOAMI_PATH)[1]                # who is here is still answered
        self.assertEqual((d["steward"], d["person"]), (False, None))
        self.assertEqual(d["people"], [{"name": "Mira", "first_time": True}])

    def test_what_is_the_units_stays_the_owners(self):
        self.as_mira()
        self.Mira.seen[:] = []
        for path in sorted(serve.OWNER_ONLY_POST) + [serve.SHUTDOWN_PATH]:
            status, d = self.req("POST", path, {"action": "on", "confirm": "shut down"})
            self.assertEqual((status, d["code"]), (403, "owner_only"), path)
        for path in ("/aetherseed/training", "/aetherseed/cog", "/aetherseed/cog/essay?n=1"):
            self.assertEqual(self.req("GET", path)[0], 403, path)
        self.assertEqual(self.paths(self.Mira) + self.paths(self.Owner), [])
        self.assertFalse(os.path.exists(serve.SHUTDOWN_REQUEST))

    def test_the_claude_key_crosses_no_network_but_the_units_own(self):
        # 21 Nov 2026: the console on the home network is plain HTTP
        self.as_owner()
        self.Owner.seen[:] = []
        saved = serve.OWN_SCREEN
        serve.OWN_SCREEN = frozenset()          # as from a laptop on the home network
        try:
            status, d = self.req("POST", "/aetherseed/cloud", {"action": "key", "key": "sk-ant-x"})
            self.assertEqual((status, d["code"]), (403, "key_on_unit_only"))
            self.assertEqual(self.paths(self.Owner), [], "the key went nowhere")
            self.assertEqual(self.req("POST", "/aetherseed/cloud", {"action": "switch", "on": True})[0], 200)
        finally:
            serve.OWN_SCREEN = saved
        serve.OWN_SCREEN = frozenset({"127.0.0.1", "::1"})   # at the unit's own screen
        try:
            self.assertEqual(self.req("POST", "/aetherseed/cloud", {"action": "key", "key": "sk-ant-x"})[0], 200)
        finally:
            serve.OWN_SCREEN = saved
        self.assertEqual(self.paths(self.Owner).count("/aetherseed/cloud"), 2)

    def test_the_owners_brake_reaches_every_proxy(self):
        self.as_owner()
        self.assertEqual(self.req("POST", "/aetherseed/brake", {"action": "on", "reason": "test"})[0], 200)
        for backend in (self.Owner, self.Mira):
            got = [json.loads(b) for _, p, b in backend.seen if p == "/aetherseed/brake"]
            self.assertEqual(got, [{"action": "on", "reason": "test"}])

    def test_a_member_the_owner_removed_is_nobody_again(self):
        self.as_mira()
        people.save([])
        self.assertEqual(self.req("GET", "/aetherseed/memories")[0], 401)
        self.assertEqual(self.req("POST", "/api/chat",
                                  {"messages": [{"role": "user", "content": "Hi"}]})[0], 401)
        self.assertIsNone(self.req("GET", serve.WHOAMI_PATH)[1]["person"])

    def test_signing_out_ends_it(self):
        self.as_mira()
        self.assertEqual(self.req("POST", serve.SIGNOUT_PATH, {})[0], 200)
        self.assertEqual(self.req("GET", "/aetherseed/memories", cookie=False)[0], 401)


class AtTheUnitsOwnScreen(_Unit):

    def setUp(self):
        super().setUp()
        serve.OWN_SCREEN = frozenset({"127.0.0.1", "::1"})

    def test_the_own_screen_is_the_owner_until_a_member_signs_in_there(self):
        self.assertEqual(self.req("GET", serve.WHOAMI_PATH)[1]["person"], {"role": "owner"})
        self.assertEqual(self.req("GET", "/aetherseed/memories")[0], 200)
        self.assertEqual(self.req("POST", "/api/chat",          # the own screen talks, as the owner
                                  {"messages": [{"role": "user", "content": "Hi"}]})[1]["whose"], "Samuel")
        self.assertEqual(self.paths(self.Mira), [])
        self.as_mira()
        self.Owner.seen[:] = []
        self.assertEqual(self.req("GET", serve.WHOAMI_PATH)[1]["person"], {"role": "member", "name": "Mira"})
        self.assertEqual(self.req("GET", "/aetherseed/memories")[0], 200)
        self.assertEqual(self.req("POST", "/aetherseed/brake", {"action": "on"})[0], 403)
        self.assertEqual(self.paths(self.Owner), [])
        self.assertEqual(self.req("POST", serve.SIGNOUT_PATH, {})[0], 200)
        self.assertEqual(self.req("GET", serve.WHOAMI_PATH, cookie=False)[1]["person"], {"role": "owner"})


class OneModelForEveryRoot(unittest.TestCase):

    def test_two_proxies_cannot_hold_the_model_at_once(self):
        from test_memory_turn import proxy          # the real proxy module
        import time
        tmp = tempfile.mkdtemp(prefix="lock-")
        try:
            path = os.path.join(tmp, "model.lock")
            a, b = proxy._OneCallerAtATime(path), proxy._OneCallerAtATime(path)   # two processes' locks
            order = []

            def second():
                with b:
                    order.append("b in")
            with a:
                t = threading.Thread(target=second)
                t.start()
                time.sleep(0.3)
                order.append("a out")
            t.join(5)
            self.assertEqual(order, ["a out", "b in"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_without_the_shared_file_it_is_the_lock_it_always_was(self):
        from test_memory_turn import proxy
        lock = proxy._OneCallerAtATime("/nonexistent-dir/model.lock")
        with lock:
            self.assertIsNone(lock._fd)
        with lock:                                   # released, and taken again
            pass


class TheInstaller(unittest.TestCase):
    # tools/people.py enables aetherseed-proxy@<id>: the installer must have
    # put the unit there, and the folders the running console and proxy see

    def test_it_installs_the_units_and_folders_people_need(self):
        here = os.path.dirname(os.path.abspath(__file__))
        sh = open(os.path.join(here, "install.sh"), encoding="utf-8").read()
        self.assertIn('"$SRC/services/aetherseed-proxy@.service"', sh)
        self.assertIn("/var/lib/aetherseed-keys", sh)
        self.assertIn("/var/lib/aetherseed-people /etc/aetherseed/people", sh)
        self.assertTrue(os.path.exists(os.path.join(here, "services", "aetherseed-proxy@.service")))
        # installed for nobody: a person's proxy is started by the owner's tool
        starting = sh.split('echo "Starting"')[1]
        # enabled for nobody: none is named after the start; when the model
        # changed, the ones that were running (and only those) start again
        self.assertEqual([l.strip() for l in starting.splitlines() if "aetherseed-proxy@" in l], [])
        self.assertIn("PEOPLE_UP=$(systemctl list-units 'aetherseed-proxy@*' --state=active", sh)
        self.assertIn("systemctl start $PEOPLE_UP", starting)


if __name__ == "__main__":
    unittest.main()


class TheToolsTheDocsTellToRun(unittest.TestCase):
    """INSTALL and the console tell the owner to run these by their path."""
    def test_they_can_be_run_by_their_path(self):
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("people.py", "steward_key.py"):
            mode = subprocess.run(["git", "ls-files", "-s", "tools/" + name], cwd=here,
                                  capture_output=True, text=True).stdout.split(" ")[0]
            if mode:                                  # in a git checkout: the mode git keeps
                self.assertEqual(mode, "100755", name)
            else:                                     # in a release: the file's own mode
                self.assertTrue(os.access(os.path.join(here, "tools", name), os.X_OK), name)
