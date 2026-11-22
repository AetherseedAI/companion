"""The first start of a unit onboarded where it will live.

    python3 -m unittest test_first_start -v


Three parts, each tried without a Pi, a radio or root's clock:

  - the console server takes the date and time and the passkey only at the
    unit's own screen, only on a unit armed for a first start, files them
    for root and waits for root's answer;
  - tools/first_start.sh, root's side, with the clock and the Wi-Fi tool
    stood in for;
  - tools/source_card.sh refuses to make a source of a unit that has been
    started.

Standard library only.
"""
import http.client
import http.server
import importlib.util
import io
import json
import shutil
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICES = os.path.join(HERE, "services")
FIRST_START = os.path.join(HERE, "tools", "first_start.sh")
SOURCE_CARD = os.path.join(HERE, "tools", "source_card.sh")

_spec = importlib.util.spec_from_file_location("serve_fs", os.path.join(HERE, "gui", "serve.py"))
serve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve)
# no members here, whatever the machine running the tests has (gui/people.py)
serve.people.PEOPLE_FILE = "/nonexistent/people.json"

KEY = "correct horse 42"
OWN = "my own steward key 7"     # the steward's own passkey: not the Wi-Fi's
ADMIN = "fieldkeeper"
APW = "a long admin password 7"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class _Elsewhere(serve.Console):
    """The same console, asked from a screen that is not the unit's own."""
    def _own_screen(self):
        return False


class _OnTheSetupNetwork(serve.Console):
    """A phone on the unit's own (setup) network: not its own screen."""
    def _own_screen(self):
        return False

    def _on_own_wifi(self):
        return True


class AtTheConsole(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.flag = os.path.join(self.tmp, "first-start")
        self.request = os.path.join(self.tmp, "first-start-request")
        self.result = os.path.join(self.tmp, "first-start-result")
        self._was = (serve.FIRST_START_FLAG, serve.FIRST_START_REQUEST,
                     serve.FIRST_START_RESULT, serve.FIRST_START_WAIT, serve.CSP)
        serve.FIRST_START_FLAG, serve.FIRST_START_REQUEST = self.flag, self.request
        serve.FIRST_START_RESULT, serve.FIRST_START_WAIT = self.result, 3.0
        serve.CSP = "default-src 'none'"
        self.srv = serve.Threaded(("127.0.0.1", 0), serve.Console)
        self.far = serve.Threaded(("127.0.0.1", 0), _Elsewhere)
        self.phone = serve.Threaded(("127.0.0.1", 0), _OnTheSetupNetwork)
        self.setup_key = os.path.join(self.tmp, "setup-wifi.key")
        self._was_key = serve.SETUP_KEY
        serve.SETUP_KEY = self.setup_key
        for s in (self.srv, self.far, self.phone):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        self.seen = None            # what root's side read from the request

    def tearDown(self):
        serve.SETUP_KEY = self._was_key
        for s in (self.srv, self.far, self.phone):
            s.shutdown(); s.server_close()
        (serve.FIRST_START_FLAG, serve.FIRST_START_REQUEST, serve.FIRST_START_RESULT,
         serve.FIRST_START_WAIT, serve.CSP) = self._was

    def arm(self):
        open(self.flag, "w").close()

    def call(self, method="POST", body=None, srv=None, ctype="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", (srv or self.srv).server_address[1], timeout=20)
        data = json.dumps(body).encode() if body is not None else None
        c.request(method, "/aetherseed/first-start", body=data,
                  headers={"Content-Type": ctype} if data is not None else {})
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"{}"))
        c.close()
        return out

    def root(self, answer):
        """Root's side, stood in for: takes the request, leaves an answer."""
        def work():
            for _ in range(200):
                if os.path.exists(self.request):
                    self.mode = stat.S_IMODE(os.stat(self.request).st_mode)
                    with open(self.request, encoding="utf-8") as f:
                        self.seen = f.read()
                    os.unlink(self.request)
                    with open(self.result, "w", encoding="utf-8") as f:
                        f.write(answer)
                    return
                time.sleep(0.02)
        threading.Thread(target=work, daemon=True).start()

    # ---- what the page is told ----------------------------------------------
    def test_a_unit_that_was_set_up_at_a_shell_is_not_asked(self):
        status, d = self.call("GET")
        self.assertEqual(status, 200)
        self.assertEqual((d["armed"], d["own_screen"]), (False, True))
        self.assertRegex(d["now"], r"^20\d\d-\d\d-\d\dT\d\d:\d\d$")

    def test_an_armed_unit_says_so_and_says_whose_screen_is_asking(self):
        self.arm()
        self.assertEqual(self.call("GET")[1]["armed"], True)
        self.assertEqual(self.call("GET", srv=self.far)[1]["own_screen"], False)

    # ---- the three locks -------------------------------------------------------
    def test_only_at_the_units_own_screen(self):
        self.arm()
        status, d = self.call(body={"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, srv=self.far)
        self.assertEqual((status, d["code"]), (403, "not_own_screen"))
        self.assertFalse(os.path.exists(self.request))

    def test_only_on_a_unit_armed_for_it(self):
        status, d = self.call(body={"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d["code"]), (409, "not_armed"))
        self.assertFalse(os.path.exists(self.request))

    def test_only_a_date_and_time_and_a_passkey(self):
        self.arm()
        for body, code in (
            ({"when": "2026-02-31T10:00", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, "bad_when"),
            ({"when": "1999-01-01T10:00", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, "bad_when"),
            ({"when": "2026-10-07T24:00", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, "bad_when"),
            ({"when": "2026-10-07T15:30\n2026-01-01 00:00", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, "bad_when"),
            ({"when": "now", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, "bad_when"),
            ({"passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW}, "bad_when"),
            ({"when": "2026-10-07T15:30", "passkey": "seven77"}, "bad_passkey"),
            ({"when": "2026-10-07T15:30", "passkey": "x" * 64}, "bad_passkey"),
            ({"when": "2026-10-07T15:30", "passkey": "åtte tegn"}, "bad_passkey"),
            ({"when": "2026-10-07T15:30", "passkey": "two\nlines here"}, "bad_passkey"),
            ({"when": "2026-10-07T15:30", "passkey": 12345678}, "bad_passkey"),
            ({"when": "2026-10-07T15:30"}, "bad_passkey"),
            # the steward's own passkey is required, and is not the Wi-Fi's
            ({"when": "2026-10-07T15:30", "passkey": KEY}, "bad_steward_key"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": "seven77"}, "bad_steward_key"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": "x" * 64}, "bad_steward_key"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": "åtte tegn"}, "bad_steward_key"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": 12345678}, "bad_steward_key"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": KEY}, "same_key"),
            # the admin account: a login name, not one of the unit's, a long password
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN}, "bad_admin_name"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": "Field",
              "admin_password": APW}, "bad_admin_name"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": "a; rm -rf",
              "admin_password": APW}, "bad_admin_name"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": "root",
              "admin_password": APW}, "admin_taken"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": "pi",
              "admin_password": APW}, "admin_taken"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN,
              "admin_password": "short"}, "bad_admin_password"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN,
              "admin_password": "a\nlong password here"}, "bad_admin_password"),
            ({"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN,
              "admin_password": OWN}, "bad_admin_password" if len(OWN) < 12 else "same_admin_password"),
        ):
            with self.subTest(body=str(body)[:50]):
                status, d = self.call(body=body)
                self.assertEqual((status, d["code"]), (400, code))
                self.assertFalse(os.path.exists(self.request))

    def test_a_form_post_is_not_a_first_start(self):
        self.arm()
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request("POST", "/aetherseed/first-start", body=b"when=x",
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(c.getresponse().status, 415)
        c.close()

    # ---- from a phone on the setup network (21 Nov 2026) ----------------------
    def test_a_phone_on_the_setup_network_does_the_first_start(self):
        self.arm()
        self.root("ok\nBjorn\nbjorn\nlan\n")
        status, d = self.call(srv=self.phone, body={"when": "2026-10-07T15:30", "passkey": "", "network": "lan",
                                                    "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d["mode"]), (200, "lan"))
        self.assertTrue(self.seen.endswith("\nlan\n"))
        self.assertEqual(self.seen.split("\n")[1], "", "no Wi-Fi passkey for LAN only")

    def test_not_once_the_unit_has_been_started(self):
        status, d = self.call(srv=self.phone, body={"when": "2026-10-07T15:30", "passkey": KEY,
                                                    "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d["code"]), (403, "not_own_screen"))

    def test_the_setup_networks_key_is_shown_on_the_units_own_screen_only(self):
        self.arm()
        with open(self.setup_key, "w") as f:
            f.write("k7m2pq9xra\n")
        status, d = self.call(method="GET")
        self.assertEqual(d["setup"], {"ssid": "AetherSeed", "key": "k7m2pq9xra",
                                      "address": "http://10.42.0.1:2077"})
        status, d = self.call(method="GET", srv=self.phone)
        self.assertNotIn("setup", d)
        self.assertTrue(d["from_phone"])
        status, d = self.call(method="GET", srv=self.far)
        self.assertNotIn("setup", d)
        self.assertFalse(d["from_phone"])

    def test_a_network_choice_that_is_not_one_is_refused_at_the_console(self):
        self.arm()
        status, d = self.call(body={"when": "2026-10-07T15:30", "passkey": KEY, "network": "open",
                                    "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d["code"]), (400, "bad_network"))

    # ---- filed for root, and root's answer brought back ---------------------
    def test_it_is_filed_for_root_and_roots_answer_comes_back(self):
        self.arm()
        self.root("ok\nBjorn\nbjorn\n")
        said = io.StringIO()
        with redirect_stdout(said):
            status, d = self.call(body={"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d), (200, {"ok": True, "network": "Bjorn", "host": "bjorn", "mode": "hidden"}))
        self.assertEqual(self.seen, "2026-10-07 15:30\n" + KEY + "\n" + OWN + "\n" + ADMIN + "\n" + APW + "\nhidden\n")
        self.assertEqual(self.mode, 0o600, "the passkey is for root to read, and nobody else")
        self.assertNotIn(KEY, said.getvalue(), "the passkey is never logged")
        self.assertNotIn(OWN, said.getvalue(), "the steward's passkey is never logged")
        self.assertNotIn(KEY, json.dumps(d))
        self.assertNotIn(OWN, json.dumps(d))
        self.assertNotIn(APW, said.getvalue(), "the admin password is never logged")
        self.assertNotIn(APW, json.dumps(d))

    def test_what_root_refuses_is_said_in_roots_words(self):
        self.arm()
        self.root("error\nwifi\nThe unit's Wi-Fi could not be set up: no radio\n")
        status, d = self.call(body={"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d["code"]), (422, "wifi"))
        self.assertEqual(d["error"], "The unit's Wi-Fi could not be set up: no radio")

    def test_if_nobody_takes_it_the_passkey_does_not_stay_in_run(self):
        self.arm()
        serve.FIRST_START_WAIT = 0.6
        status, d = self.call(body={"when": "2026-10-07T15:30", "passkey": KEY, "steward_passkey": OWN, "admin_name": ADMIN, "admin_password": APW})
        self.assertEqual((status, d["code"]), (504, "timeout"))
        self.assertFalse(os.path.exists(self.request))

    def test_the_page_has_the_step_in_both_languages_and_names_no_address_scheme(self):
        with open(os.path.join(HERE, "gui", "index.html"), encoding="utf-8") as f:
            html = f.read()
        for needle in ('id="stepStart"', 'id="dayInput"', 'id="monthInput"', 'id="yearInput"',
                       'id="hourInput"', 'id="minuteInput"', "day: 'Day'", "day: 'Dag'",
                       'id="keyInput"', 'id="ownKeyInput"', "startTitle: (n) => `A few things", 'id="adminNameInput"', 'id="lockPiGo"',
                       "startTitle: (n) => `Noen ting før", "ownKeyHelp: (n) =>",
                       "same_key:", "bad_steward_key:", "/aetherseed/first-start"):
            self.assertIn(needle, html)
        self.assertNotIn('type="date"', html,
                         "the browser's own date box writes the day and the month in an order nobody chose")
        # The passkey is CHOSEN here, so it is typed in the open: it must be
        # read back to be written down. (Signing in with it later, on a phone
        # with guests about, is another field, and that one is hidden - build
        # log 80.)
        import re
        key_field = re.search(r'<input id="keyInput"[^>]*>', html).group(0)
        self.assertNotIn('type="password"', key_field,
                         "the passkey is typed in the open: it must be read back to be written down")


# ==============================================================================
class _Status(http.server.BaseHTTPRequestHandler):
    companion = {"configured": True, "name": "Bjørn"}

    def do_GET(self):
        body = json.dumps({"companion": self.companion}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class RootsSide(unittest.TestCase):
    """tools/first_start.sh, with the clock and the Wi-Fi tool stood in for."""

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), _Status)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self):
        _Status.companion = {"configured": True, "name": "Bjørn"}
        self.tmp = tempfile.mkdtemp()
        self.run_dir = os.path.join(self.tmp, "run"); os.makedirs(self.run_dir)
        self.flag = os.path.join(self.tmp, "first-start")
        self.log = os.path.join(self.tmp, "calls.log")
        self.hotspot = os.path.join(self.tmp, "hotspot.sh")
        self.clock = os.path.join(self.tmp, "clock.sh")
        self.steward_tool = os.path.join(self.tmp, "steward_key.py")
        self.hotspot_fails = os.path.join(self.tmp, "hotspot-fails")
        self.steward_fails = os.path.join(self.tmp, "steward-fails")
        self.add_admin = os.path.join(self.tmp, "add_admin.sh")
        self.set_host = os.path.join(self.tmp, "set_host.sh")
        self.admin_fails = os.path.join(self.tmp, "admin-fails")
        with open(self.add_admin, "w") as f:
            f.write('#!/bin/bash\nIFS= read -r p\necho "admin $1 length ${#p}" >> %s\n'
                    'printf "%%s" "$p" > %s.apw\n[ -e %s ] && exit 1\nexit 0\n'
                    % (self.log, self.log, self.admin_fails))
        with open(self.set_host, "w") as f:
            f.write('#!/bin/bash\necho "hostname $1" >> %s\n' % self.log)
        os.chmod(self.add_admin, 0o755); os.chmod(self.set_host, 0o755)
        # tools/steward_key.py own, stood in for: it takes the passkey on its input
        with open(self.steward_tool, "w") as f:
            f.write('import os, sys\nk = sys.stdin.readline().rstrip("\\n")\n'
                    'open(%r, "a").write("steward-key %%s length %%d\\n" %% (sys.argv[1], len(k)))\n'
                    'open(%r, "w").write(k)\n'
                    'sys.exit(1 if os.path.exists(%r) else 0)\n' % (self.log, self.log + ".own", self.steward_fails))
        with open(self.hotspot, "w") as f:
            f.write('#!/bin/bash\nIFS= read -r k\necho "hotspot $1 [$2] key-length ${#k}" >> %s\n'
                    'printf "%%s" "$k" > %s.key\n'
                    '[ -e %s ] && { echo "hotspot: the profile could not be written" >&2; exit 2; }\n'
                    '[ ${#k} -ge 8 ] || { echo "hotspot: not a usable passkey (8-63 plain characters)" >&2; exit 2; }\n'
                    'echo "hotspot: set up"\n' % (self.log, self.log, self.hotspot_fails))
        with open(self.clock, "w") as f:
            f.write('#!/bin/bash\necho "clock $1" >> %s\n' % self.log)
        os.chmod(self.hotspot, 0o755); os.chmod(self.clock, 0o755)

    def start(self, when="2026-10-07 15:30", key=KEY, armed=True, own=OWN, admin=ADMIN, apw=APW, net=None):
        if armed:
            open(self.flag, "w").close()
        with open(os.path.join(self.run_dir, "first-start-request"), "w") as f:
            f.write("%s\n%s\n%s\n%s\n%s\n" % (when, key, own, admin, apw))
            if net is not None:
                f.write(net + "\n")
        env = dict(os.environ, AETHERSEED_GUI_RUN=self.run_dir, AETHERSEED_FIRST_START_FLAG=self.flag,
                   AETHERSEED_HOTSPOT=self.hotspot, AETHERSEED_SET_CLOCK=self.clock,
                   AETHERSEED_STEWARD_KEY_TOOL=self.steward_tool,
                   AETHERSEED_ADD_ADMIN=self.add_admin, AETHERSEED_SET_HOSTNAME=self.set_host,
                   AETHERSEED_ADMIN_MADE=os.path.join(self.tmp, "admin-made"),
                   AETHERSEED_ADMIN_RECORD=os.path.join(self.tmp, "admin-account"),
                   AETHERSEED_SSHD_DROPIN=os.path.join(self.tmp, "sshd-dropin"),
                   AETHERSEED_SWITCH_DELAY="0",
                   AETHERSEED_STATUS_URL="http://127.0.0.1:%d/" % self.srv.server_address[1])
        p = subprocess.run(["bash", FIRST_START], env=env, capture_output=True, text=True)
        try:
            with open(os.path.join(self.run_dir, "first-start-result")) as f:
                result = f.read().split("\n")
        except OSError:
            result = None
        calls = read(self.log).splitlines() if os.path.exists(self.log) else []
        return p, result, calls

    def test_a_link_left_in_the_consoles_folder_is_never_followed(self):
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "w") as f:
            f.write("root's file\n")
        os.symlink(victim, os.path.join(self.run_dir, "first-start-result.tmp"))
        p, result, calls = self.start(armed=False)
        self.assertIsNotNone(result)
        self.assertEqual(read(victim), "root's file\n")
        req = os.path.join(self.run_dir, "first-start-request")
        os.unlink(req) if os.path.lexists(req) else None
        os.symlink(victim, req)
        env = dict(os.environ, AETHERSEED_GUI_RUN=self.run_dir, AETHERSEED_FIRST_START_FLAG=self.flag)
        p = subprocess.run(["bash", FIRST_START], env=env, capture_output=True, text=True)
        self.assertIn("a link, not a request", p.stdout)
        self.assertFalse(os.path.lexists(req))
        self.assertEqual(read(victim), "root's file\n")

    def test_the_script_is_sound(self):
        for sh in (FIRST_START, SOURCE_CARD):
            self.assertEqual(subprocess.run(["bash", "-n", sh]).returncode, 0, sh)

    def test_the_clock_then_the_wifi_then_it_is_no_longer_armed(self):
        p, result, calls = self.start()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        # the unit's own network LAST, after the answer: a phone on the setup
        # network loses it the moment the unit switches (21 Nov 2026)
        self.assertEqual(calls, ["clock 2026-10-07 15:30",
                                 "admin %s length %d" % (ADMIN, len(APW)), "hostname bjorn",
                                 "steward-key own length %d" % len(OWN),
                                 "hotspot on [Bjorn] key-length %d" % len(KEY)])
        self.assertEqual(read(self.log + ".apw"), APW, "the admin password reaches the tool on its input")
        self.assertEqual(read(os.path.join(self.tmp, "admin-account")).strip(), ADMIN)
        self.assertEqual(read(self.log + ".key"), KEY, "the passkey reaches the Wi-Fi tool on its input")
        self.assertEqual(read(self.log + ".own"), OWN, "the steward's own passkey reaches the key tool on its input")
        self.assertEqual(result[:3], ["ok", "Bjorn", "bjorn"])
        self.assertFalse(os.path.exists(self.flag), "one first start, and no second")
        self.assertNotIn(APW, p.stdout + p.stderr + "\n".join(result))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "first-start-request")))
        self.assertNotIn(KEY, p.stdout + p.stderr + "\n".join(result))
        self.assertNotIn(OWN, p.stdout + p.stderr + "\n".join(result))

    def test_a_unit_that_is_not_armed_is_left_exactly_as_it_is(self):
        p, result, calls = self.start(armed=False)
        self.assertEqual(result[:3], ["error", "not_armed", "This unit has been started before."])
        self.assertEqual(calls, [], "neither its clock nor its Wi-Fi is touched")
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "first-start-request")))

    def test_a_second_request_after_a_first_start_is_refused(self):
        self.start()
        p, result, calls = self.start(key="another passkey", armed=False)
        self.assertEqual(result[0], "error")
        self.assertEqual(len(calls), 5, "nothing was done the second time")

    def test_what_is_not_a_date_and_time_sets_nothing(self):
        for when in ("2026-02-31 10:00", "tomorrow", "2026-10-07 15:30; reboot", "",
                     "2026-10-07T15:30", "1999-12-31 23:59"):
            with self.subTest(when=when):
                p, result, calls = self.start(when=when)
                self.assertEqual(result[:2], ["error", "bad_when"])
                self.assertEqual(calls, [])
                self.assertTrue(os.path.exists(self.flag), "still armed: it can be tried again")
                if os.path.exists(self.log):
                    os.unlink(self.log)

    def test_the_stewards_own_passkey_is_asked_for_before_anything_is_changed(self):
        # not given, too short, not plain, or the Wi-Fi's
        for own, code in (("", "bad_steward_key"), ("short", "bad_steward_key"),
                          ("åtte tegn nøkkel", "bad_steward_key"), (KEY, "same_key")):
            with self.subTest(own=own):
                p, result, calls = self.start(own=own)
                self.assertEqual(result[:2], ["error", code])
                self.assertEqual(calls, [], "neither the clock, the Wi-Fi nor the key is touched")
                self.assertTrue(os.path.exists(self.flag), "still armed: it can be tried again")
                self.assertNotIn(KEY, "\n".join(result))

    def test_the_admin_account_is_checked_before_anything_is_changed(self):
        for admin, apw, code in (("Field", APW, "bad_admin_name"), ("a b", APW, "bad_admin_name"),
                                 ("", APW, "bad_admin_name"), (ADMIN, "short", "bad_admin_password"),
                                 (ADMIN, "ålange passord her", "bad_admin_password"),
                                 (ADMIN, KEY if len(KEY) >= 12 else "x" * 12, "same_admin_password"
                                  if len(KEY) >= 12 else None)):
            if code is None:
                continue
            with self.subTest(admin=admin, apw=apw[:4]):
                p, result, calls = self.start(admin=admin, apw=apw)
                self.assertEqual(result[:2], ["error", code])
                self.assertEqual(calls, [], "nothing is touched")
                self.assertTrue(os.path.exists(self.flag))
                self.assertNotIn(apw, "\n".join(result) + p.stdout + p.stderr)

    def test_an_admin_account_that_cannot_be_made_leaves_the_unit_armed(self):
        open(self.admin_fails, "w").close()
        p, result, calls = self.start()
        self.assertEqual(result[:2], ["error", "admin"])
        self.assertTrue(os.path.exists(self.flag))
        self.assertNotIn("steward-key own length %d" % len(OWN), calls)

    def test_the_hostname_is_the_companions_name_for_the_network(self):
        for name, host in (("Bjørn", "bjorn"), ("Åse-Marie", "ase-marie"), ("Zoë O'Neil", "zoe-oneil")):
            with self.subTest(name=name):
                _Status.companion = {"configured": True, "name": name}
                p, result, calls = self.start()
                self.assertIn("hostname %s" % host, calls)
                self.assertEqual(result[2], host)
                os.unlink(self.log)

    def test_a_steward_key_that_cannot_be_set_leaves_the_unit_armed(self):
        open(self.steward_fails, "w").close()
        p, result, calls = self.start()
        self.assertEqual(result[:2], ["error", "steward_key"])
        self.assertTrue(os.path.exists(self.flag), "the Wi-Fi is up, and the first start can be done again")
        self.assertNotIn(OWN, "\n".join(result) + p.stdout + p.stderr)

    def test_a_passkey_the_wifi_tool_refuses_leaves_the_unit_armed(self):
        p, result, calls = self.start(key="short")
        self.assertEqual(result[:3], ["error", "bad_passkey", "The passkey must be 8 to 63 plain characters."])
        self.assertTrue(os.path.exists(self.flag))

    def test_a_wifi_that_will_not_come_up_is_said_and_can_be_tried_again(self):
        open(self.hotspot_fails, "w").close()
        p, result, calls = self.start()
        # the answer went first; the switch failed after it: the unit is armed
        # again and keeps its setup network, so the first start can be redone
        self.assertEqual(result[:2], ["ok", "Bjorn"])
        self.assertIn("armed again", p.stdout)
        self.assertIn("the profile could not be written", p.stdout)
        self.assertTrue(os.path.exists(self.flag))
        self.assertNotIn(KEY, "\n".join(result) + p.stdout + p.stderr)

    def test_a_visible_network_when_the_owner_chose_it(self):
        p, result, calls = self.start(net="visible")
        self.assertEqual(result[:4], ["ok", "Bjorn", "bjorn", "visible"])
        self.assertEqual(calls[-1], "hotspot on [--visible] key-length %d" % len(KEY))

    def test_lan_only_needs_no_wifi_passkey_and_takes_the_network_away(self):
        with open(self.hotspot, "w") as f:      # a cable is linked: LAN only is possible
            f.write('#!/bin/bash\nIFS= read -r k\necho "hotspot $1 [$2] key-length ${#k}" >> %s\nexit 0\n' % self.log)
        p, result, calls = self.start(key="", net="lan")
        self.assertEqual(result[:4], ["ok", "Bjorn", "bjorn", "lan"])
        self.assertEqual(calls[0], "hotspot can-lan [] key-length 0")
        self.assertEqual(calls[-1], "hotspot off [--lan] key-length 0")

    def test_lan_only_is_refused_where_it_would_strand_the_unit(self):
        with open(self.hotspot, "a") as f:
            pass
        # the stand-in says no cable and no home Wi-Fi for can-lan
        with open(self.hotspot, "w") as f:
            f.write('#!/bin/bash\necho "hotspot $1 [$2]" >> %s\n[ "$1" = can-lan ] && exit 1\nexit 0\n' % self.log)
        p, result, calls = self.start(key="", net="lan")
        self.assertEqual(result[:2], ["error", "lan_unreachable"])
        self.assertTrue(os.path.exists(self.flag))
        self.assertEqual(calls, ["hotspot can-lan []"])

    def test_a_network_choice_that_is_not_one_is_refused(self):
        p, result, calls = self.start(net="open")
        self.assertEqual(result[:2], ["error", "bad_network"])
        self.assertEqual(calls, [])

    def test_the_networks_name_is_the_companions_in_plain_letters(self):
        for name, network in (("Bjørn", "Bjorn"), ("Åse-Marie", "Ase-Marie"), ("Aria", "Aria"),
                              ("Zoë O'Neil", "Zoe ONeil"), ("Ærø", "Aero")):
            with self.subTest(name=name):
                _Status.companion = {"configured": True, "name": name}
                p, result, calls = self.start()
                self.assertEqual(result[:2], ["ok", network])
                os.unlink(self.log)

    def test_a_unit_with_no_name_yet_is_told_to_name_it_first(self):
        _Status.companion = {"configured": False, "name": None}
        p, result, calls = self.start()
        self.assertEqual(result[:3], ["error", "no_name", "Name your companion first."])
        self.assertEqual([c for c in calls if c.startswith("hotspot")], [])
        self.assertTrue(os.path.exists(self.flag))

    def test_with_no_request_it_does_nothing(self):
        open(self.flag, "w").close()
        env = dict(os.environ, AETHERSEED_GUI_RUN=self.run_dir, AETHERSEED_FIRST_START_FLAG=self.flag,
                   AETHERSEED_HOTSPOT=self.hotspot, AETHERSEED_SET_CLOCK=self.clock)
        p = subprocess.run(["bash", FIRST_START], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertFalse(os.path.exists(self.log))
        self.assertTrue(os.path.exists(self.flag))


# ==============================================================================
@unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0, "the seal is root's")
class ACardThatIsASource(unittest.TestCase):
    """tools/source_card.sh seal, as a dry run: what it refuses."""

    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.etc = tempfile.mkdtemp()

    def seal(self, *more):
        env = dict(os.environ, AETHERSEED_STATE=self.state, AETHERSEED_ETC=self.etc, AETHERSEED_DRY="1")
        return subprocess.run(["bash", SOURCE_CARD, "seal"] + list(more), env=env,
                              capture_output=True, text=True)

    def test_a_seal_that_is_only_tried_restarts_and_says_it_is_not_a_card_to_copy(self):
        self.store(0)
        p = self.seal("--restart")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would: systemctl --no-block reboot", p.stdout)
        self.assertNotIn("poweroff", p.stdout)
        self.assertIn("NOT a card to copy", p.stdout)

    def store(self, turns):
        import sqlite3
        d = os.path.join(self.state, ".aetherseed", "aetherroot"); os.makedirs(d)
        c = sqlite3.connect(os.path.join(d, "memory.db"))
        c.execute("create table episodes (id integer primary key, user_msg text)")
        c.executemany("insert into episodes (user_msg) values (?)", [("x",)] * turns)
        c.commit(); c.close()

    def test_a_unit_that_never_started_is_sealed(self):
        self.store(0)
        p = self.seal()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for needle in ("would: touch %s/first-start %s/new-identity" % (self.etc, self.etc),
                       "would: systemctl enable aetherseed-first-start.path aetherseed-new-identity.service",
                       "would: rm -f /etc/ssh/ssh_host_", "would: systemctl --no-block poweroff"):
            self.assertIn(needle, p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.etc, "first-start")), "a dry run changes nothing")

    def test_the_setup_network_is_no_wifi_of_its_own_and_each_copy_makes_its_own(self):
        self.store(0)
        b = tempfile.mkdtemp()
        with open(os.path.join(b, "nmcli"), "w") as f:
            f.write("#!/bin/bash\ncase \"$*\" in\n"
                    "  \"-t -f NAME,TYPE connection show\") echo aetherseed-setup:802-11-wireless ;;\n"
                    "  \"-t -f NAME connection show\") echo aetherseed-setup ;;\nesac\n")
        os.chmod(os.path.join(b, "nmcli"), 0o755)
        env = dict(os.environ, PATH=b + os.pathsep + os.environ["PATH"], AETHERSEED_STATE=self.state,
                   AETHERSEED_ETC=self.etc, AETHERSEED_DRY="1")
        p = subprocess.run(["bash", SOURCE_CARD, "seal"], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would: nmcli connection delete aetherseed-setup", p.stdout)
        self.assertIn("would: rm -f %s/setup-wifi.key" % self.etc, p.stdout)

    def test_a_named_companion_is_never_made_a_source(self):
        self.store(0)
        with open(os.path.join(self.state, ".aetherseed", "companion.json"), "w") as f:
            json.dump({"name": "Aria", "language": "en"}, f)
        p = self.seal()
        self.assertEqual(p.returncode, 2)
        self.assertIn("its companion is named (Aria)", p.stderr)
        self.assertNotIn("would:", p.stdout, "nothing is even begun")

    def test_a_memory_with_a_turn_in_it_is_never_made_a_source(self):
        self.store(3)
        p = self.seal()
        self.assertEqual(p.returncode, 2)
        self.assertIn("its memory holds 3 turn(s)", p.stderr)
        self.assertNotIn("would:", p.stdout)

    def test_a_stewards_document_or_a_trust_record_stops_it_too(self):
        os.makedirs(os.path.join(self.state, "aetherseed-shelf"))
        open(os.path.join(self.state, "aetherseed-shelf", "physics.pdf"), "w").close()
        os.makedirs(os.path.join(self.state, ".aetherseed"))
        with open(os.path.join(self.state, ".aetherseed", "trust_state.json"), "w") as f:
            f.write("{}")
        p = self.seal()
        self.assertEqual(p.returncode, 2)
        self.assertIn("1 document(s) of a steward", p.stderr)
        self.assertIn("it has a trust record", p.stderr)


class TheUnits(unittest.TestCase):
    def unit(self, name):
        with open(os.path.join(SERVICES, name), encoding="utf-8") as f:
            return [l.strip() for l in f.read().splitlines() if l.strip() and not l.lstrip().startswith("#")]

    def test_the_path_watches_the_consoles_request_and_starts_roots_side(self):
        d = self.unit("aetherseed-first-start.path")
        self.assertIn("PathExists=/run/aetherseed-gui/first-start-request", d)
        self.assertIn("Unit=aetherseed-first-start.service", d)
        s = self.unit("aetherseed-first-start.service")
        self.assertIn("ExecStart=/bin/bash /opt/aetherseed/tools/first_start.sh", s)
        self.assertEqual([l for l in s if l.startswith("User=")], [], "it is root's, and says so by saying nothing")
        self.assertEqual(serve.FIRST_START_REQUEST, "/run/aetherseed-gui/first-start-request")

    def test_a_new_identity_only_where_a_seal_asked_for_one(self):
        d = self.unit("aetherseed-new-identity.service")
        self.assertIn("ConditionPathExists=/etc/aetherseed/new-identity", d)
        self.assertIn("WantedBy=sysinit.target", d)
        before = [l for l in d if l.startswith("Before=")][0]
        for u in ("ssh.service", "NetworkManager.service"):
            self.assertIn(u, before)
        last = [l for l in d if l.startswith("ExecStart=")][-1]
        self.assertIn("rm -f /etc/aetherseed/new-identity", last)
        self.assertIn("[ ! -e /etc/aetherseed/new-identity ] &&", last,
                      "it restarts only once the flag is gone, or it would restart for ever")


    def test_the_passkey_is_written_nowhere_by_roots_side(self):
        text = read(FIRST_START)
        self.assertNotIn('echo "$key', text)
        self.assertNotIn("logger", text)
        self.assertEqual(text.count('printf \'%s\\n\' "$key" | "$HOTSPOT" on'), 2)   # hidden, visible


class LockingTheDefaultAccount(unittest.TestCase):
    """tools/lock_default.sh: run by the admin through sudo, it locks pi."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.record = os.path.join(self.tmp, "admin-account")
        with open(self.record, "w") as f:
            f.write(ADMIN + "\n")
        self.log = os.path.join(self.tmp, "lock.log")
        self.tool = os.path.join(self.tmp, "usermod")
        with open(self.tool, "w") as f:
            f.write('#!/bin/bash\necho "$*" >> %s\n' % self.log)
        os.chmod(self.tool, 0o755)

    def run_as(self, sudo_user, uid0=True):
        here = os.path.dirname(os.path.abspath(__file__))
        env = dict(os.environ, AETHERSEED_ADMIN_RECORD=self.record, AETHERSEED_LOCK_TOOL=self.tool)
        env.pop("SUDO_USER", None)
        if sudo_user:
            env["SUDO_USER"] = sudo_user
        cmd = [os.path.join(here, "tools", "lock_default.sh")]
        if not uid0 or os.geteuid() != 0:
            self.skipTest("needs root in the test environment") if os.geteuid() != 0 else None
        p = subprocess.run(cmd, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout, read(self.log) if os.path.exists(self.log) else ""

    def test_the_admin_locks_pi(self):
        rc, out, log = self.run_as(ADMIN)
        self.assertEqual(rc, 0, out)
        self.assertEqual(log.strip(), "-L -e 1 pi")
        self.assertIn("Way back", out)

    def test_nobody_else_can(self):
        for who in ("pi", "someone", None):
            with self.subTest(who=who):
                rc, out, log = self.run_as(who)
                self.assertNotEqual(rc, 0)
                self.assertIn("nothing locked", out)
                self.assertEqual(log, "")

    def test_without_a_recorded_admin_nothing_is_locked(self):
        os.unlink(self.record)
        rc, out, log = self.run_as(ADMIN)
        self.assertNotEqual(rc, 0)
        self.assertEqual(log, "")


if __name__ == "__main__":
    unittest.main()
