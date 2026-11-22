"""A home Wi-Fi from the console: root's side (tools/wifi.py).

    python3 -m unittest test_wifi -v
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "tools", "wifi.py")

FAKE_NMCLI = r'''#!/bin/bash
printf 'nmcli' >> "$LOG"; printf ' %q' "$@" >> "$LOG"; echo >> "$LOG"
case "$*" in
  "-t -f SSID,SIGNAL,SECURITY device wifi list ifname wlan0") [ -e "$RADIO" ] && cat "$SCAN" 2>/dev/null ;;
  "radio wifi") [ -e "$RADIO" ] && echo enabled || echo disabled ;;
  "radio wifi on") touch "$RADIO" ;;
  "radio wifi off") rm -f "$RADIO" ;;
esac
exit 0
'''
FAKE_HOTSPOT = '#!/bin/bash\necho "hotspot $*" >> "$LOG"\n'
FAKE_SYSTEMCTL = '#!/bin/bash\necho "systemctl $*" >> "$LOG"\n'


class RootsSide(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wifi-")
        self.run = os.path.join(self.tmp, "run")
        self.gui = os.path.join(self.run, "aetherseed-gui")
        self.nm = os.path.join(self.tmp, "nm")
        self.bin = os.path.join(self.tmp, "bin")
        for d in (self.gui, self.bin):
            os.makedirs(d)
        self.log = os.path.join(self.tmp, "log")
        open(self.log, "w").close()
        self.scan = os.path.join(self.tmp, "scan")
        for name, body in (("nmcli", FAKE_NMCLI), ("hotspot.sh", FAKE_HOTSPOT),
                           ("systemctl", FAKE_SYSTEMCTL)):
            p = os.path.join(self.bin, name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, 0o755)
        self.request = os.path.join(self.gui, "wifi-request")
        self.result = os.path.join(self.gui, "wifi-result")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ask(self, obj=None, raw=None):
        if raw is None and obj is not None:
            raw = json.dumps(obj)
        if raw is not None:
            fd = os.open(self.request, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(raw)
        env = dict(os.environ, LOG=self.log, SCAN=self.scan, AETHERSEED_WIFI_REQUEST=self.request,
                   AETHERSEED_WIFI_RESULT=self.result, AETHERSEED_NM_DIR=self.nm,
                   AETHERSEED_NMCLI=os.path.join(self.bin, "nmcli"),
                   AETHERSEED_HOTSPOT_TOOL=os.path.join(self.bin, "hotspot.sh"),
                   AETHERSEED_SYSTEMCTL=os.path.join(self.bin, "systemctl"),
                   AETHERSEED_WIFI_SWITCH_DELAY="0", AETHERSEED_WIFI_SCAN_WAKE="0",
                   AETHERSEED_WIFI_SCAN_WAIT="0", RADIO=os.path.join(self.tmp, "radio"),
                   AETHERSEED_HOTSPOT_LOCK=os.path.join(self.tmp, "lock"),
                   AETHERSEED_WIFI_NAME=os.path.join(self.tmp, "etc", "wifi-home"))
        r = subprocess.run([sys.executable, TOOL], env=env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.result) as f:
            return json.load(f), r

    def logged(self):
        with open(self.log) as f:
            return f.read()

    def profile(self):
        with open(os.path.join(self.nm, "aetherseed-home.nmconnection")) as f:
            return f.read()

    def test_a_home_network_is_saved_and_the_radio_follows_the_rule(self):
        res, r = self.ask({"action": "join", "ssid": "Home_Net-54D539", "password": "correct horse 9"})
        self.assertEqual(res, {"ok": True, "action": "join", "ssid": "Home_Net-54D539"})
        p = os.path.join(self.nm, "aetherseed-home.nmconnection")
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
        text = self.profile()
        self.assertIn("id=aetherseed-home", text)
        self.assertIn("autoconnect=false", text)
        self.assertIn("key-mgmt=wpa-psk", text)
        self.assertIn("psk=correct horse 9", text)
        self.assertIn("ssid=" + ";".join(str(b) for b in b"Home_Net-54D539") + ";", text)
        with open(os.path.join(self.tmp, "etc", "wifi-home")) as f:
            self.assertEqual(f.read(), "Home_Net-54D539\n")      # the name, for the console
        log = self.logged()
        self.assertIn("nmcli connection reload", log)
        self.assertIn("hotspot sync", log)
        # the rule runs from now on, on a unit set up without a network of its own too
        self.assertIn("systemctl enable --now wpa_supplicant", log)
        self.assertIn("systemctl enable --now aetherseed-hotspot", log)
        self.assertLess(log.index("enable --now aetherseed-hotspot"), log.index("hotspot sync"))
        self.assertFalse(os.path.exists(self.request))

    def test_the_password_is_never_on_a_command_line_or_in_the_result_or_log(self):
        res, r = self.ask({"action": "join", "ssid": "Kitchen", "password": "s3cret-pass-word"})
        for where in (self.logged(), json.dumps(res), r.stdout, r.stderr):
            self.assertNotIn("s3cret-pass-word", where)

    def test_a_name_with_spaces_and_quotes_and_a_password_with_a_backslash(self):
        ssid = 'Ida\'s "net" 2'
        self.ask({"action": "join", "ssid": ssid, "password": " back\\slash "})
        text = self.profile()
        self.assertIn("ssid=" + ";".join(str(b) for b in ssid.encode()) + ";", text)
        self.assertIn("psk=\\sback\\\\slash\\s", text)

    def test_an_open_network_has_no_password(self):
        self.ask({"action": "join", "ssid": "Cafe", "password": ""})
        self.assertNotIn("wifi-security", self.profile())

    def test_what_is_not_a_wifi_password_saves_nothing(self):
        for pw in ("short", "x" * 64, "line\nbreak1"):
            res, _ = self.ask({"action": "join", "ssid": "Home", "password": pw})
            self.assertEqual(res["code"], "bad_password")
        res, _ = self.ask({"action": "join", "ssid": "", "password": "longenough"})
        self.assertEqual(res["code"], "bad_ssid")
        res, _ = self.ask({"action": "join", "ssid": "x" * 33, "password": "longenough"})
        self.assertEqual(res["code"], "bad_ssid")
        self.assertFalse(os.path.exists(os.path.join(self.nm, "aetherseed-home.nmconnection")))
        self.assertNotIn("hotspot sync", self.logged())

    def test_forget_removes_it(self):
        self.ask({"action": "join", "ssid": "Home", "password": "longenough"})
        res, _ = self.ask({"action": "forget"})
        self.assertEqual(res, {"ok": True, "action": "forget"})
        self.assertFalse(os.path.exists(os.path.join(self.nm, "aetherseed-home.nmconnection")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "etc", "wifi-home")))
        self.assertIn("nmcli connection delete aetherseed-home", self.logged())

    def test_a_scan_lists_each_network_once_strongest_first(self):
        with open(self.scan, "w") as f:
            f.write("Home_Net-54D539:100:WPA2\nFjelberg:92:WPA2 WPA3\nHome_Net-54D539:60:WPA2\n"
                    "::40:WPA2\nCafe\\:Bar:30:\n")
        res, _ = self.ask({"action": "scan"})
        self.assertEqual(res["networks"], [
            {"ssid": "Home_Net-54D539", "signal": 100, "secure": True},
            {"ssid": "Fjelberg", "signal": 92, "secure": True},
            {"ssid": "Cafe:Bar", "signal": 30, "secure": False}])
        self.assertNotIn("hotspot", self.logged())
        # the radio was off (a cable is in): on for the scan, off again after
        log = self.logged()
        self.assertLess(log.index("radio wifi on"), log.index("device wifi list"))
        self.assertLess(log.index("device wifi list"), log.index("radio wifi off"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "radio")))

    def test_a_radio_that_is_on_is_left_on(self):
        open(os.path.join(self.tmp, "radio"), "w").close()
        self.ask({"action": "scan"})
        self.assertNotIn("radio wifi off", self.logged())

    def test_a_request_through_a_link_is_never_followed(self):
        target = os.path.join(self.tmp, "elsewhere")
        with open(target, "w") as f:
            f.write(json.dumps({"action": "forget"}))
        os.symlink(target, self.request)
        res, _ = self.ask()
        self.assertEqual(res["code"], "no_request")
        self.assertTrue(os.path.exists(target))

    def test_a_link_left_where_the_result_goes_is_replaced_not_followed(self):
        target = os.path.join(self.tmp, "victim")
        with open(target, "w") as f:
            f.write("keep")
        os.symlink(target, self.result)
        self.ask({"action": "scan"})
        with open(target) as f:
            self.assertEqual(f.read(), "keep")
        self.assertFalse(os.path.islink(self.result))

    def test_what_is_not_a_request_does_nothing(self):
        res, _ = self.ask(raw="not json")
        self.assertEqual(res["code"], "bad_request")
        res, _ = self.ask({"action": "reboot"})
        self.assertEqual(res["code"], "bad_request")
        self.assertEqual(self.logged(), "")


class TheUnits(unittest.TestCase):

    def test_the_path_watches_the_consoles_request_and_starts_roots_side(self):
        with open(os.path.join(HERE, "services", "aetherseed-wifi.path")) as f:
            p = f.read()
        self.assertIn("PathExists=/run/aetherseed-gui/wifi-request", p)
        self.assertIn("Unit=aetherseed-wifi.service", p)
        with open(os.path.join(HERE, "services", "aetherseed-wifi.service")) as f:
            s = f.read()
        self.assertIn("ExecStart=/usr/bin/python3 /opt/aetherseed/tools/wifi.py", s)
        self.assertIn("Type=oneshot", s)
        with open(os.path.join(HERE, "install.sh")) as f:
            i = f.read()
        self.assertIn("aetherseed-wifi.path", i)
        self.assertIn("aetherseed-wifi.path aetherseed-wifi.service aetherseed-hotspot.service", i)


sys.path.insert(0, os.path.join(HERE, "gui"))
import importlib.util as _u
_spec = _u.spec_from_file_location("serve_wifi", os.path.join(HERE, "gui", "serve.py"))
serve = _u.module_from_spec(_spec)
_spec.loader.exec_module(serve)
import contextlib, http.client, io, threading, time  # noqa: E402


class _OnItsOwnWifi(serve.Console):
    """A phone on the unit's hidden network: it knew the name and the passkey."""
    def _own_screen(self):
        return False

    def _on_own_wifi(self):
        return True


class _OnTheHomeNetwork(serve.Console):
    """Somebody on the cable or home network, not signed in."""
    def _own_screen(self):
        return False

    def _on_own_wifi(self):
        return False


class AtTheConsole(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = lambda n: os.path.join(self.tmp, n)
        self.req, self.res, self.state, self.name = p("req"), p("res"), p("state"), p("name")
        self._was = (serve.WIFI_REQUEST, serve.WIFI_RESULT, serve.WIFI_STATE, serve.WIFI_NAME,
                     serve.WIFI_WAIT, serve.CSP)
        serve.WIFI_REQUEST, serve.WIFI_RESULT, serve.WIFI_STATE, serve.WIFI_NAME = (
            self.req, self.res, self.state, self.name)
        serve.WIFI_WAIT, serve.CSP = 3.0, "default-src 'none'"
        serve._wifi_joins.clear()
        self.servers = {k: serve.Threaded(("127.0.0.1", 0), c) for k, c in
                        (("screen", serve.Console), ("phone", _OnItsOwnWifi), ("lan", _OnTheHomeNetwork))}
        for s in self.servers.values():
            threading.Thread(target=s.serve_forever, daemon=True).start()

    def tearDown(self):
        for s in self.servers.values():
            s.shutdown(); s.server_close()
        (serve.WIFI_REQUEST, serve.WIFI_RESULT, serve.WIFI_STATE, serve.WIFI_NAME,
         serve.WIFI_WAIT, serve.CSP) = self._was

    def call(self, method, body=None, where="screen"):
        c = http.client.HTTPConnection("127.0.0.1", self.servers[where].server_address[1], timeout=20)
        c.request(method, "/aetherseed/wifi", body=json.dumps(body).encode() if body is not None else None,
                  headers={"Content-Type": "application/json"})
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"{}"))
        c.close()
        return out

    def root(self, answer):
        self.seen = None
        def work():
            for _ in range(200):
                if os.path.exists(self.req):
                    self.mode = stat.S_IMODE(os.stat(self.req).st_mode)
                    self.seen = json.load(open(self.req))
                    os.unlink(self.req)
                    with open(self.res, "w") as f:
                        json.dump(answer, f)
                    return
                time.sleep(0.02)
        threading.Thread(target=work, daemon=True).start()

    def test_a_phone_on_its_hidden_network_puts_it_on_the_home_wifi(self):
        self.root({"ok": True, "action": "join", "ssid": "Home"})
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            status, d = self.call("POST", {"action": "join", "ssid": "Home", "password": "pass phrase 1"},
                                  where="phone")
        self.assertEqual((status, d), (200, {"ok": True, "action": "join", "ssid": "Home"}))
        self.assertEqual(self.seen, {"action": "join", "ssid": "Home", "password": "pass phrase 1"})
        self.assertEqual(self.mode, 0o600)
        self.assertNotIn("pass phrase 1", said.getvalue())

    def test_not_from_the_home_network_unless_signed_in_as_the_steward(self):
        status, d = self.call("POST", {"action": "join", "ssid": "Home", "password": "pass phrase 1"},
                              where="lan")
        self.assertEqual((status, d["code"]), (403, "not_here"))
        status, d = self.call("GET", where="lan")
        self.assertEqual(status, 403)
        self.assertFalse(os.path.exists(self.req))

    def test_only_the_screen_or_the_steward_forgets_it(self):
        status, d = self.call("POST", {"action": "forget"}, where="phone")
        self.assertEqual((status, d["code"]), (403, "steward_only"))
        self.root({"ok": True, "action": "forget"})
        status, d = self.call("POST", {"action": "forget"})
        self.assertEqual(status, 200)

    def test_what_is_not_a_network_or_a_password_is_not_sent(self):
        for body, code in (({"action": "join", "ssid": "", "password": "longenough"}, "bad_ssid"),
                           ({"action": "join", "ssid": "x" * 33, "password": "longenough"}, "bad_ssid"),
                           ({"action": "join", "ssid": "Home", "password": "short"}, "bad_password"),
                           ({"action": "join", "ssid": "Home", "password": 12345678}, "bad_password"),
                           ({"action": "reboot"}, "bad_request")):
            status, d = self.call("POST", body)
            self.assertEqual((status, d["code"]), (400, code))
        self.assertFalse(os.path.exists(self.req))

    def test_ten_joins_an_hour(self):
        for _ in range(10):
            self.root({"ok": True, "action": "join", "ssid": "Home"})
            self.call("POST", {"action": "join", "ssid": "Home", "password": "longenough"})
        status, d = self.call("POST", {"action": "join", "ssid": "Home", "password": "longenough"})
        self.assertEqual((status, d["code"]), (429, "too_many"))

    def test_no_answer_leaves_no_password_behind(self):
        status, d = self.call("POST", {"action": "join", "ssid": "Home", "password": "longenough"})
        self.assertEqual((status, d["code"]), (504, "timeout"))
        self.assertFalse(os.path.exists(self.req))

    def test_what_the_radio_serves_and_the_home_networks_name(self):
        with open(self.state, "w") as f:
            f.write("serving=own\nat=1\nhome_last=failed\nhome_failed_at=1\n")
        with open(self.name, "w") as f:
            f.write("Home_Net-54D539\n")
        status, d = self.call("GET", where="phone")
        self.assertEqual((status, d), (200, {"serving": "own", "home": "Home_Net-54D539",
                                             "home_last": "failed", "may_forget": False}))


if __name__ == "__main__":
    unittest.main()
