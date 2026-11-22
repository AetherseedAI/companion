"""Locking the image's pi account from the onboarding (tools/lock_pi_request.py,
the console's /aetherseed/lock-pi). 15 Nov 2026."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APW = "a long admin password 7"


class RootsSide(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = lambda n: os.path.join(self.tmp, n)
        self.req, self.res, self.rec, self.log = p("req"), p("res"), p("admin"), p("lock.log")
        with open(self.rec, "w") as f:
            f.write("fieldkeeper\n")
        self.check = p("check.sh")
        with open(self.check, "w") as f:
            f.write('#!/bin/bash\nIFS= read -r pw\n[ "$pw" = "%s" ]\n' % APW)
        self.lock = p("usermod")
        with open(self.lock, "w") as f:
            f.write('#!/bin/bash\necho "$*" >> %s\n' % self.log)
        os.chmod(self.check, 0o755); os.chmod(self.lock, 0o755)

    def run_it(self, pw, members="fieldkeeper", status="P"):
        with open(self.req, "w") as f:
            f.write(pw + "\n")
        env = dict(os.environ, AETHERSEED_LOCK_PI_REQUEST=self.req, AETHERSEED_LOCK_PI_RESULT=self.res,
                   AETHERSEED_ADMIN_RECORD=self.rec, AETHERSEED_SIGNIN_CHECK=self.check,
                   AETHERSEED_LOCK_TOOL=self.lock, AETHERSEED_SUDO_MEMBERS=members,
                   AETHERSEED_PASSWD_STATUS=status)
        p = subprocess.run([sys.executable, os.path.join(HERE, "tools", "lock_pi_request.py")],
                           env=env, capture_output=True, text=True)
        res = open(self.res).read().split("\n")
        log = open(self.log).read() if os.path.exists(self.log) else ""
        self.assertFalse(os.path.exists(self.req), "the request with the password is gone")
        self.assertNotIn(APW, p.stdout + p.stderr + "\n".join(res))
        return res, log

    def test_the_right_password_locks_pi(self):
        res, log = self.run_it(APW)
        self.assertEqual(res[:2], ["ok", "locked"])
        self.assertEqual(log.strip(), "-L -e 1 pi")

    def test_a_wrong_password_changes_nothing(self):
        res, log = self.run_it("not the password at all")
        self.assertEqual(res[:2], ["error", "wrong_password"])
        self.assertEqual(log, "")

    def test_an_admin_without_sudo_changes_nothing(self):
        res, log = self.run_it(APW, members="someoneelse")
        self.assertEqual(res[:2], ["error", "not_sudo"])
        self.assertEqual(log, "")

    def test_already_locked(self):
        res, log = self.run_it(APW, status="L")
        self.assertEqual(res[:2], ["ok", "already"])
        self.assertEqual(log, "")

    def test_no_recorded_admin(self):
        os.unlink(self.rec)
        res, log = self.run_it(APW)
        self.assertEqual(res[:2], ["error", "no_admin"])
        self.assertEqual(log, "")

    def test_a_link_left_in_the_consoles_folder_is_never_followed(self):
        # The folder is the console's (unprivileged); this runs as root. A
        # link where root writes its answer must not be written through.
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "w") as f:
            f.write("root's file\n")
        os.symlink(victim, self.res + ".tmp")
        res, log = self.run_it(APW)
        self.assertEqual(res[:2], ["ok", "locked"])
        self.assertEqual(open(victim).read(), "root's file\n")
        # and a request that is a link is not read
        os.symlink(victim, self.req)
        env = dict(os.environ, AETHERSEED_LOCK_PI_REQUEST=self.req, AETHERSEED_LOCK_PI_RESULT=self.res,
                   AETHERSEED_ADMIN_RECORD=self.rec, AETHERSEED_SIGNIN_CHECK=self.check,
                   AETHERSEED_LOCK_TOOL=self.lock, AETHERSEED_SUDO_MEMBERS="fieldkeeper",
                   AETHERSEED_PASSWD_STATUS="P")
        subprocess.run([sys.executable, os.path.join(HERE, "tools", "lock_pi_request.py")],
                       env=env, capture_output=True)
        self.assertEqual(open(self.res).read().split("\n")[:2], ["error", "no_request"])
        self.assertFalse(os.path.lexists(self.req))
        self.assertEqual(open(victim).read(), "root's file\n")

    def test_it_is_installed_and_watched(self):
        sh = open(os.path.join(HERE, "install.sh"), encoding="utf-8").read()
        self.assertIn("aetherseed-lock-pi.path aetherseed-lock-pi.service", sh)
        self.assertIn("aetherseed-lock-pi.path", sh.split("systemctl enable --now")[1].splitlines()[0])
        path = open(os.path.join(HERE, "services", "aetherseed-lock-pi.path")).read()
        self.assertIn("PathExists=/run/aetherseed-gui/lock-pi-request", path)


sys.path.insert(0, os.path.join(HERE, "gui"))
import importlib.util as _u
_spec = _u.spec_from_file_location("serve_lockpi", os.path.join(HERE, "gui", "serve.py"))
serve = _u.module_from_spec(_spec)
_spec.loader.exec_module(serve)
import http.client, io, contextlib, stat, threading, time


class _Elsewhere(serve.Console):
    def _own_screen(self):
        return False


class AtTheConsole(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.req, self.res = os.path.join(self.tmp, "req"), os.path.join(self.tmp, "res")
        self._was = (serve.LOCK_PI_REQUEST, serve.LOCK_PI_RESULT, serve.LOCK_PI_WAIT, serve.CSP)
        serve.LOCK_PI_REQUEST, serve.LOCK_PI_RESULT, serve.LOCK_PI_WAIT = self.req, self.res, 3.0
        serve.CSP = "default-src 'none'"
        serve._lock_pi_tries.clear()
        self.srv = serve.Threaded(("127.0.0.1", 0), serve.Console)
        self.far = serve.Threaded(("127.0.0.1", 0), _Elsewhere)
        for s in (self.srv, self.far):
            threading.Thread(target=s.serve_forever, daemon=True).start()

    def tearDown(self):
        for s in (self.srv, self.far):
            s.shutdown(); s.server_close()
        serve.LOCK_PI_REQUEST, serve.LOCK_PI_RESULT, serve.LOCK_PI_WAIT, serve.CSP = self._was

    def post(self, body, srv=None):
        c = http.client.HTTPConnection("127.0.0.1", (srv or self.srv).server_address[1], timeout=20)
        c.request("POST", "/aetherseed/lock-pi", body=json.dumps(body).encode(),
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
                    self.seen = open(self.req).read()
                    os.unlink(self.req)
                    open(self.res, "w").write(answer)
                    return
                time.sleep(0.02)
        threading.Thread(target=work, daemon=True).start()

    def test_the_password_goes_to_root_and_nowhere_else(self):
        self.root("ok\nlocked\npi\n")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            status, d = self.post({"admin_password": APW})
        self.assertEqual((status, d), (200, {"ok": True, "state": "locked"}))
        self.assertEqual(self.seen, APW + "\n")
        self.assertEqual(self.mode, 0o600)
        self.assertNotIn(APW, said.getvalue())

    def test_only_at_the_units_own_screen(self):
        status, d = self.post({"admin_password": APW}, srv=self.far)
        self.assertEqual((status, d["code"]), (403, "not_own_screen"))
        self.assertFalse(os.path.exists(self.req))

    def test_a_bad_password_is_not_sent(self):
        for pw in ("short", "x" * 129, "ålange passord her", None, 12345678901234):
            status, d = self.post({"admin_password": pw})
            self.assertEqual((status, d["code"]), (400, "bad_admin_password"))
        self.assertFalse(os.path.exists(self.req))

    def test_five_wrong_tries_an_hour(self):
        for i in range(5):
            self.root("error\nwrong_password\nThat is not the admin's password.\n")
            status, d = self.post({"admin_password": APW})
            self.assertEqual((status, d["code"]), (422, "wrong_password"))
        status, d = self.post({"admin_password": APW})
        self.assertEqual((status, d["code"]), (429, "too_many"))

    def test_no_answer_leaves_no_password_behind(self):
        status, d = self.post({"admin_password": APW})
        self.assertEqual((status, d["code"]), (504, "timeout"))
        self.assertFalse(os.path.exists(self.req))


if __name__ == "__main__":
    unittest.main()
