"""No unit in the build depends on a person's account.

 Until the kiosk ran as samuel - his home
and UID 1000 written into the unit - and the keepalive ran as samuel from
his home. A deployment unit would have needed an account with his name, with
passwordless sudo, behind the screen.

These read the unit files as shipped and fail if one runs as, or names the
home or runtime directory of, anyone but the build's own two accounts.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICES = os.path.join(HERE, "services")
ACCOUNTS = {"aetherseed", "aetherseed-kiosk"}      # created at install


def units():
    for name in sorted(os.listdir(SERVICES)):
        if name.endswith((".service", ".path")):
            with open(os.path.join(SERVICES, name), encoding="utf-8") as f:
                yield name, f.read()


def directives(text):
    """Every line that is not a comment - continuation lines included."""
    return [l.strip() for l in text.splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def unit(name):
    with open(os.path.join(SERVICES, name), encoding="utf-8") as f:
        return directives(f.read())


class TestNoPersonInTheBuild(unittest.TestCase):

    def test_every_account_a_unit_runs_as_is_the_builds_own(self):
        seen = 0
        for name, text in units():
            for line in directives(text):
                m = re.match(r"(User|Group)=(\S+)$", line)
                if m:
                    seen += 1
                    self.assertIn(m.group(2), ACCOUNTS, "%s: %s" % (name, line))
        self.assertGreater(seen, 0)

    def test_no_unit_names_a_home_or_a_uid(self):
        for name, text in units():
            for line in directives(text):
                self.assertNotRegex(line, r"/home/", "%s: %s" % (name, line))
                self.assertNotRegex(line, r"/run/user/\d", "%s: %s" % (name, line))
                self.assertNotRegex(line, r"\bsamuel\b", "%s: %s" % (name, line))

    def test_the_browser_waits_for_the_page_it_shows(self):
        #started in the same second as the console server, the
        # browser asked too early and stayed on a blank page.
        d = unit("aetherseed-kiosk.service")
        text = " ".join(d)
        pre = text.index("ExecStartPre=/usr/bin/curl")
        self.assertLess(pre, text.index("ExecStart=/usr/bin/labwc"))
        wait = text[pre:text.index("ExecStart=/usr/bin/labwc")]
        self.assertIn("http://127.0.0.1:2077/", wait)
        self.assertIn("--retry-connrefused", wait)
        self.assertIn("--fail", wait)
        self.assertIn("--app=http://127.0.0.1:2077/", text)   # the same page
        # and for the network to settle first: a load cut off by the address
        # arriving left the blank page, 3 boots of 3. Failing must not stop
        # the screen ("-"), and it waits for start-up, not for a connection.
        net = text.index("ExecStartPre=-/usr/bin/nm-online -s -q")
        self.assertLess(net, pre)
        self.assertIn("Restart=always", d)

    def test_the_screen_is_restarted_when_the_console_is_not_on_it(self):
        #now, kiosk since, console server since, last poll -> restart?
        import subprocess
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "kiosk_watch.sh")
        self.assertEqual(subprocess.run(["bash", "-n", sh]).returncode, 0)
        cases = (((1000, 0, 900, 0), 0),       # the screen is not running
                 ((1000, 950, 0, 0), 0),       # no console server to show
                 ((1000, 950, 900, 0), 0),     # the browser has only just started
                 ((1000, 800, 800, 0), 1),     # up 200 s and never polled: the blank page
                 ((1000, 800, 800, 995), 0),   # polling
                 ((1000, 800, 800, 905), 1),   # stopped polling 95 s ago
                 ((1000, 100, 990, 50), 0),    # the console server was just restarted
                 ((1000, 100, 100, 911), 0))   # 89 s: not yet
        for args, want in cases:
            with self.subTest(args=args):
                r = subprocess.run(["bash", sh, "--decide"] + [str(a) for a in args])
                self.assertEqual(r.returncode, want)
        text = open(sh).read()
        self.assertEqual(text.count("systemctl restart"), 1)
        self.assertNotIn("rm ", text)

    def test_the_watch_unit_runs_the_installed_script_and_nothing_else(self):
        d = unit("aetherseed-kiosk-watch.service")
        self.assertIn("ExecStart=/bin/bash /opt/aetherseed/tools/kiosk_watch.sh", d)
        self.assertIn("Restart=always", d)
        self.assertIn("WantedBy=multi-user.target", d)
        self.assertFalse(any(l.startswith("User=") for l in d))   # root: it restarts a unit

    def test_the_scale_of_the_screen_is_the_units_own(self):
        # One unit file for every unit; a unit that was told nothing runs at
        # scale 3, and /etc/aetherseed/kiosk.env sets another.
        d = unit("aetherseed-kiosk.service")
        self.assertIn("Environment=AETHERSEED_SCALE=3", d)
        self.assertIn("EnvironmentFile=-/etc/aetherseed/kiosk.env", d)     # "-": it may be absent
        self.assertLess(d.index("Environment=AETHERSEED_SCALE=3"),
                        d.index("EnvironmentFile=-/etc/aetherseed/kiosk.env"))   # the file wins
        flags = [l for l in d if "--force-device-scale-factor" in l and not l.startswith("#")]
        self.assertEqual([l.strip() for l in flags],
                         ["--force-device-scale-factor=${AETHERSEED_SCALE} \\"])

    def test_the_kiosk_runs_as_its_own_account_with_its_own_profile(self):
        d = unit("aetherseed-kiosk.service")
        self.assertIn("User=aetherseed-kiosk", d)
        self.assertIn("PAMName=login", d)          # XDG_RUNTIME_DIR comes from here
        self.assertIn("RuntimeDirectory=aetherseed-kiosk", d)
        self.assertTrue(any("--user-data-dir=/run/aetherseed-kiosk/" in l for l in d))
        self.assertFalse(any(l.startswith("Environment=HOME=") for l in d))
        self.assertFalse(any(l.startswith("Environment=XDG_RUNTIME_DIR=") for l in d))

    def test_the_keepalive_runs_as_the_service_account_from_the_application(self):
        d = unit("aetherseed-keepalive.service")
        self.assertIn("User=aetherseed", d)
        self.assertIn("SupplementaryGroups=video", d)     # vcgencmd: /dev/vcio_gencmd
        self.assertIn("StateDirectory=aetherseed-keepalive", d)
        self.assertIn("Environment=KEEPALIVE_DIR=/var/lib/aetherseed-keepalive", d)
        self.assertIn("ExecStart=/usr/bin/python3 /opt/aetherseed/tools/keepalive.py", d)
        self.assertTrue(os.path.isfile(os.path.join(HERE, "tools", "keepalive.py")))
        self.assertTrue(os.path.isfile(os.path.join(HERE, "tools", "power.py")))


def chain(rules, name):
    """The directives of one chain of services/nftables.conf."""
    i = rules.index("chain %s {" % name)
    return rules[i + 1:rules.index("}", i)]


class TheUnitsOwnWifi(unittest.TestCase):
    """a phone on the unit's own Wi-Fi is a second screen.

    The console unit and the firewall are two halves of one line: the console
    listens on every address, and the firewall names who reaches it.
    """

    def setUp(self):
        with open(os.path.join(SERVICES, "nftables.conf"), encoding="utf-8") as f:
            self.rules = directives(f.read())

    def test_the_console_listens_beyond_loopback(self):
        d = unit("aetherseed-gui.service")
        self.assertIn("Environment=AETHERSEED_GUI_BIND=0.0.0.0", d)
        self.assertIn("Environment=AETHERSEED_BACKEND=http://127.0.0.1:8001", d)
        # the proxy and the model stay where they were
        self.assertFalse(any("0.0.0.0" in l for l in unit("aetherseed-proxy.service")))
        self.assertFalse(any("0.0.0.0" in l for l in unit("hailo-ollama.service")))

    def test_the_console_is_admitted_from_the_units_wifi_and_the_private_ranges(self):
        # 15 Nov 2026: and from the home network's private ranges (--lan; the
        # console listens on 127.0.0.1 without it)
        port = [l for l in self.rules if "2077" in l]
        self.assertEqual(port, ['iifname "wlan0" tcp dport 2077 accept',
                                "tcp dport 2077 ip saddr @lan4 accept",
                                "tcp dport 2077 ip6 saddr @lan6 accept"])
        dhcp = [l for l in chain(self.rules, "input") if "dport 67" in l]
        self.assertEqual(dhcp, ['iifname "wlan0" udp dport 67 accept'])
        # everything admitted, line by line: a new one is added here on purpose
        accepts = [l for l in chain(self.rules, "input") if l.endswith("accept")]
        self.assertEqual(accepts, [
            'iif "lo" accept',
            "ct state established,related accept",
            "meta l4proto icmpv6 accept",
            "meta l4proto icmp accept",
            "udp dport 68 accept",
            "tcp dport 22 ip saddr @lan4 accept",
            "tcp dport 22 ip6 saddr @lan6 accept",
            'iifname "wlan0" udp dport 67 accept',
            'iifname "wlan0" tcp dport 2077 accept',
            "tcp dport 2077 ip saddr @lan4 accept",
            "tcp dport 2077 ip6 saddr @lan6 accept",
            # its name on the local network (mDNS), 15 Nov 2026
            "udp dport 5353 ip saddr @lan4 accept",
            "udp dport 5353 ip6 saddr @lan6 accept",
        ])
        import re as _re
        # no name service offered; the only port-53 lines are the companion's
        # own lookups going out, for Claude (21 Nov 2026)
        self.assertFalse(any(_re.search(r"dport 53\b", l) for l in chain(self.rules, "input")))
        self.assertTrue(all('meta skuid "aetherseed"' in l or 'meta skuid "systemd-timesync"' in l
                            for l in self.rules if _re.search(r"dport (\{ )?53\b", l)))

    def test_nothing_passes_through_the_unit(self):
        # NetworkManager's shared mode switches forwarding on; this is what
        # keeps a phone on the unit's Wi-Fi out of the cable network.
        self.assertEqual(chain(self.rules, "forward"),
                         ["type filter hook forward priority filter; policy drop;"])
        self.assertIn("type filter hook input priority filter; policy drop;", self.rules)

    def test_the_hotspot_tool_checks_what_it_is_given(self):
        import subprocess
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "hotspot.sh")
        self.assertEqual(subprocess.run(["bash", "-n", sh]).returncode, 0)

        def check(name, key):
            return subprocess.run(["bash", sh, "--check", name], input=key + "\n",
                                  text=True, capture_output=True).returncode
        self.assertEqual(check("Nova", "eight888"), 0)
        self.assertEqual(check("My Companion", "x" * 63), 0)
        for name, key in (("", "eight888"), ("x" * 33, "eight888"),
                          ("Nova", "seven77"), ("Nova", "x" * 64),
                          ('St"ella', "eight888"), ("St\\ella", "eight888"),
                          (" Nova", "eight888"), ("Nóva", "eight888"),
                          ("Nova", "eight88\u00e9"), ("Nova", "")):
            with self.subTest(name=name, key=len(key)):
                self.assertEqual(check(name, key), 2)

    def test_the_passkey_is_nowhere_but_the_profile(self):
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "hotspot.sh")
        text = open(sh, encoding="utf-8").read()
        self.assertEqual(text.count('wifi-sec.psk "$key"'), 1)
        self.assertNotIn("echo \"$key", text)
        self.assertNotIn("tee", text)
        # wlan0 only, WPA2 only, and it does not touch the firewall itself
        self.assertIn("wifi-sec.proto rsn", text)
        self.assertNotIn("nft ", text)


class ItsWifiOnlyWhileNoCableIsLinked(unittest.TestCase):
    """. 

    tools/hotspot.sh is run here with a NetworkManager made of files: what it
    would switch is recorded, and nothing is switched.
    """

    FAKE_NMCLI = r'''#!/bin/bash
echo "nmcli $*" >> "$LOG"
case "$*" in
  "-t -f NAME connection show") [ -e "$STATE/profile" ] && echo aetherseed-hotspot ;;
  "-t -f NAME connection show --active") [ -e "$STATE/up" ] && echo aetherseed-hotspot ;;
  "radio wifi") [ -e "$STATE/radio" ] && echo enabled || echo disabled ;;
  "radio wifi on") touch "$STATE/radio" ;;
  "radio wifi off") rm -f "$STATE/radio" ;;
  "connection up aetherseed-hotspot") [ -e "$STATE/radio" ] && touch "$STATE/up" || exit 4 ;;
  "connection down aetherseed-hotspot") rm -f "$STATE/up" ;;
esac
exit 0
'''

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="hotspot-")
        self.bin = os.path.join(self.tmp, "bin")
        self.state = os.path.join(self.tmp, "state")
        self.net = os.path.join(self.tmp, "net")
        for d in (self.bin, self.state):
            os.makedirs(d)
        for name, body in (("nmcli", self.FAKE_NMCLI), ("id", "#!/bin/bash\necho 0\n"),
                           ("sleep", "#!/bin/bash\nexit 0\n")):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(body)
            os.chmod(path, 0o755)
        # a wired port, the radio, the loopback - as the kernel shows them
        self._port("eth0", kind="1", carrier="1", device=True)
        self._port("wlan0", kind="1", carrier="1", device=True, wireless=True)
        self._port("lo", kind="772", carrier="1", device=False)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _port(self, name, kind, carrier, device, wireless=False):
        d = os.path.join(self.net, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "type"), "w") as f:
            f.write(kind + "\n")
        if carrier is not None:
            with open(os.path.join(d, "carrier"), "w") as f:
                f.write(carrier + "\n")
        elif os.path.exists(os.path.join(d, "carrier")):
            os.remove(os.path.join(d, "carrier"))
        if device:
            os.makedirs(os.path.join(d, "device"), exist_ok=True)
        if wireless:
            os.makedirs(os.path.join(d, "wireless"), exist_ok=True)

    def _have(self, *names):
        for n in names:
            open(os.path.join(self.state, n), "w").close()

    def _sync(self, what="sync", settle="30"):
        import subprocess
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "hotspot.sh")
        log = os.path.join(self.tmp, "log")
        open(log, "w").close()
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], LOG=log,
                   STATE=self.state, AETHERSEED_NET_DIR=self.net, AETHERSEED_SETTLE=settle,
                   NET=self.net, AETHERSEED_WIFI_STATE=os.path.join(self.tmp, "wifi-state"),
                   AETHERSEED_HOTSPOT_LOCK=os.path.join(self.tmp, "lock"), **getattr(self, "extra_env", {}))
        args = what if isinstance(what, list) else [what]
        r = subprocess.run(["bash", sh] + args, env=env, text=True, capture_output=True,
                           input=getattr(self, "stdin_text", None))
        with open(log) as f:
            did = [l.strip()[6:] for l in f if not l.startswith("nmcli -t") and l.strip() != "nmcli radio wifi"]
        return r, did, sorted(os.listdir(self.state))

    def test_a_cable_with_a_link_switches_the_radio_off(self):
        self._have("profile", "radio", "up")
        r, did, state = self._sync()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(did, ["connection down aetherseed-hotspot", "radio wifi off"])
        self.assertEqual(state, ["profile"])
        self.assertIn("the radio is off", r.stdout)
        # and once it is off, nothing more is switched or said
        r, did, _ = self._sync()
        self.assertEqual((did, r.stdout), ([], ""))

    def test_no_cable_with_a_link_brings_it_up(self):
        self._have("profile")
        self._port("eth0", kind="1", carrier="0", device=True)
        r, did, state = self._sync()
        self.assertEqual(did, ["radio wifi on", "connection up aetherseed-hotspot"])
        self.assertEqual(state, ["profile", "radio", "up"])
        self.assertIn("Wi-Fi is up", r.stdout)
        r, did, _ = self._sync()                       # already up: left alone
        self.assertEqual((did, r.stdout), ([], ""))

    def test_a_port_that_cannot_be_read_is_no_link(self):
        self._have("profile")
        self._port("eth0", kind="1", carrier=None, device=True)    # the port is switched off
        _, did, state = self._sync()
        self.assertIn("up", state)

    def test_the_radio_is_not_a_cable(self):
        # wlan0 has a carrier while the access point is up; it must not count
        self._have("profile", "radio", "up")
        self._port("eth0", kind="1", carrier="0", device=True)
        _, did, state = self._sync()
        self.assertEqual((did, state), ([], ["profile", "radio", "up"]))

    def test_a_unit_with_no_wifi_of_its_own_is_left_alone(self):
        self._have("radio")                             # no profile
        self._port("eth0", kind="1", carrier="0", device=True)
        r, did, state = self._sync()
        self.assertEqual((r.returncode, did, state), (0, [], ["radio"]))

    def test_at_start_a_cable_is_given_time_to_find_its_link(self):
        # On a unit the port found its link fifteen seconds after the unit came
        # up, and the Wi-Fi was up with the cable in for fourteen of them.
        self._have("profile")
        self._port("eth0", kind="1", carrier="0", device=True)
        # a second passes; at the third the cable has its link
        with open(os.path.join(self.bin, "sleep"), "w") as f:
            f.write('#!/bin/bash\necho x >> "$STATE/../slept"\n'
                    '[ "$(wc -l < "$STATE/../slept")" -ge 3 ] && echo 1 > "$NET/eth0/carrier"\nexit 0\n')
        r, did, state = self._sync("start")
        self.assertEqual((did, state), ([], ["profile"]))          # the radio never came on
        with open(os.path.join(self.tmp, "slept")) as f:
            self.assertEqual(len(f.read().split()), 3)

    def test_at_start_with_no_cable_it_comes_up_after_the_wait(self):
        self._have("profile")
        self._port("eth0", kind="1", carrier="0", device=True)
        with open(os.path.join(self.bin, "sleep"), "w") as f:
            f.write('#!/bin/bash\necho x >> "$STATE/../slept"\nexit 0\n')
        r, did, state = self._sync("start", settle="5")
        self.assertEqual(did, ["radio wifi on", "connection up aetherseed-hotspot"])
        with open(os.path.join(self.tmp, "slept")) as f:
            self.assertEqual(len(f.read().split()), 5)             # waited the whole of it first

    def test_networkmanager_never_raises_it_by_itself(self):
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "hotspot.sh")
        text = open(sh, encoding="utf-8").read()
        self.assertIn("connection.autoconnect no", text)
        self.assertNotIn("connection.autoconnect yes", text)

    def test_the_unit_that_applies_it(self):
        d = unit("aetherseed-hotspot.service")
        self.assertIn("ExecStart=/bin/bash /opt/aetherseed/tools/hotspot.sh watch", d)
        self.assertIn("After=NetworkManager.service", d)
        self.assertIn("Restart=always", d)
        self.assertIn("WantedBy=multi-user.target", d)


class TheSetupNetwork(ItsWifiOnlyWhileNoCableIsLinked):
    """21 Nov 2026: "the unit can be AetherSeed on the wifi unhidden until first
    connection, then the user can decide whether to have it broadcasting
    hidden, not hidden or LAN only." Visible, but with a key shown on the
    unit's own screen: the first start sends passkeys over it."""

    FAKE_NMCLI = r"""#!/bin/bash
echo "nmcli $*" >> "$LOG"
case "$*" in
  "-t -f NAME connection show")
    [ -e "$STATE/profile" ] && echo aetherseed-hotspot
    [ -e "$STATE/setup" ] && echo aetherseed-setup
    [ -e "$STATE/home" ] && echo aetherseed-home ;;
  "-t -f NAME connection show --active")
    [ -e "$STATE/up" ] && echo aetherseed-hotspot
    [ -e "$STATE/setupup" ] && echo aetherseed-setup ;;
  "-t -f NAME,TYPE connection show") : ;;
  "radio wifi") [ -e "$STATE/radio" ] && echo enabled || echo disabled ;;
  "radio wifi on") touch "$STATE/radio" ;;
  "radio wifi off") rm -f "$STATE/radio" ;;
  "connection up aetherseed-hotspot") [ -e "$STATE/radio" ] && touch "$STATE/up" || exit 4 ;;
  "connection down aetherseed-hotspot") rm -f "$STATE/up" ;;
  "connection up aetherseed-setup") [ -e "$STATE/radio" ] && touch "$STATE/setupup" || exit 4 ;;
  "connection delete aetherseed-setup") rm -f "$STATE/setup" "$STATE/setupup" ;;
  "connection delete aetherseed-hotspot") rm -f "$STATE/profile" "$STATE/up" ;;
  connection\ add*aetherseed-setup*) touch "$STATE/setup"; echo "$*" > "$STATE/setup-args" ;;
  connection\ add*aetherseed-hotspot*) touch "$STATE/profile"; echo "$*" > "$STATE/profile-args" ;;
esac
exit 0
"""

    def setUp(self):
        super().setUp()
        for name, body in (("systemctl", "#!/bin/bash\necho \"systemctl $*\" >> \"$LOG\"\nexit 0\n"),
                           ("chgrp", "#!/bin/bash\nexit 0\n"),
                           ("curl", "#!/bin/bash\nexit 1\n")):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(body)
            os.chmod(path, 0o755)
        self.flag = os.path.join(self.tmp, "first-start")
        self.key = os.path.join(self.tmp, "setup-wifi.key")
        self.extra_env = {"AETHERSEED_FIRST_START_FLAG": self.flag, "AETHERSEED_SETUP_KEY": self.key}

    def test_an_armed_unit_shows_aetherseed_visible_with_a_key_of_its_own(self):
        open(self.flag, "w").close()
        r, did, state = self._sync("setup")
        self.assertEqual(r.returncode, 0, r.stderr)
        args = open(os.path.join(self.state, "setup-args")).read()
        self.assertIn("ssid AetherSeed", args)
        self.assertIn("802-11-wireless.hidden no", args)
        self.assertIn("wifi-sec.key-mgmt wpa-psk", args)
        key = open(self.key).read()
        self.assertRegex(key, r"^[a-km-np-z2-9]{10}$")
        self.assertIn("wifi-sec.psk " + key, args)
        self.assertEqual(oct(os.stat(self.key).st_mode & 0o777), "0o640")

    def test_not_on_a_unit_that_is_not_armed(self):
        r, did, state = self._sync("setup")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not armed", r.stderr)
        self.assertNotIn("setup", state)

    def test_the_rule_serves_the_setup_network_until_the_unit_has_its_own(self):
        open(self.flag, "w").close()
        self._have("setup")
        self._port("eth0", kind="1", carrier="0", device=True)
        r, did, state = self._sync()
        self.assertIn("connection up aetherseed-setup", did)
        self.assertIn("setupup", state)

    def test_armed_the_setup_network_stays_up_with_a_cable_in(self):
        open(self.flag, "w").close()
        self._have("setup")
        self._port("eth0", kind="1", carrier="1", device=True)
        r, did, state = self._sync()
        self.assertIn("connection up aetherseed-setup", did)
        self.assertIn("setupup", state)
        self.assertNotIn("radio wifi off", did)

    def test_its_own_network_hidden_or_visible_takes_the_setup_one_away(self):
        for flag, hidden in (([], "yes"), (["--visible"], "no")):
            with self.subTest(visible=bool(flag)):
                self._have("setup"); open(self.key, "w").write("abcdefghjk")
                self.stdin_text = "a passkey of hers\n"
                r, did, state = self._sync(["on"] + flag + ["Aria"])
                self.assertEqual(r.returncode, 0, r.stderr)
                args = open(os.path.join(self.state, "profile-args")).read()
                self.assertIn("ssid Aria", args)
                self.assertIn("802-11-wireless.hidden " + hidden, args)
                self.assertNotIn("setup", state)
                self.assertFalse(os.path.exists(self.key))

    def test_lan_only_is_refused_where_it_would_strand_the_unit(self):
        self._have("setup")
        self._port("eth0", kind="1", carrier="0", device=True)
        r, did, state = self._sync(["off", "--lan"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unreachable", r.stderr)
        self.assertIn("setup", state)
        r, did, state = self._sync("can-lan")
        self.assertEqual(r.returncode, 1)

    def test_lan_only_with_a_cable_linked(self):
        self._have("setup", "profile")
        self._port("eth0", kind="1", carrier="1", device=True)
        r, did, state = self._sync(["off", "--lan"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("setup", state)
        self.assertNotIn("profile", state)


class AHomeWifiFirstThenItsOwn(ItsWifiOnlyWhileNoCableIsLinked):
    """16 Nov 2026: "The unit should be able to connect to the wifi regardless."
    A cable first; else the home Wi-Fi it was given; else its own hidden
    network, so it is never left unreachable."""

    FAKE_NMCLI = r'''#!/bin/bash
echo "nmcli $*" >> "$LOG"
case "$*" in
  "-t -f NAME connection show")
    [ -e "$STATE/profile" ] && echo aetherseed-hotspot
    [ -e "$STATE/home" ] && echo aetherseed-home ;;
  "-t -f NAME connection show --active")
    [ -e "$STATE/up" ] && echo aetherseed-hotspot
    [ -e "$STATE/homeup" ] && echo aetherseed-home ;;
  "radio wifi") [ -e "$STATE/radio" ] && echo enabled || echo disabled ;;
  "radio wifi on") touch "$STATE/radio" ;;
  "radio wifi off") rm -f "$STATE/radio" ;;
  "connection up aetherseed-hotspot") [ -e "$STATE/radio" ] && touch "$STATE/up" || exit 4 ;;
  "connection down aetherseed-hotspot") rm -f "$STATE/up" ;;
  "--wait 40 connection up aetherseed-home")
    [ -e "$STATE/radio" ] && [ -e "$STATE/answers" ] && { rm -f "$STATE/up"; touch "$STATE/homeup"; } || exit 4 ;;
  "connection down aetherseed-home") rm -f "$STATE/homeup" ;;
esac
exit 0
'''

    def setUp(self):
        super().setUp()
        iw = os.path.join(self.bin, "iw")
        with open(iw, "w") as f:
            f.write('#!/bin/bash\n[ -e "$STATE/phone" ] && echo "Station aa:bb:cc:dd:ee:ff (on wlan0)"\nexit 0\n')
        os.chmod(iw, 0o755)

    def _wifi_state(self):
        try:
            with open(os.path.join(self.tmp, "wifi-state")) as f:
                return dict(l.rstrip("\n").split("=", 1) for l in f if "=" in l)
        except OSError:
            return {}

    def _states(self, state):
        return [x for x in state if x not in ("answers", "phone")]

    def test_the_home_wifi_is_joined_when_no_cable_is_linked(self):
        self._port("eth0", kind="1", carrier="0", device=True)     # no cable
        self._have("profile", "home", "answers")
        r, did, state = self._sync()
        self.assertEqual(did, ["radio wifi on", "--wait 40 connection up aetherseed-home"])
        self.assertEqual(self._states(state), ["home", "homeup", "profile", "radio"])
        self.assertIn("home Wi-Fi", r.stdout)
        self.assertEqual(self._wifi_state().get("serving"), "home")
        r, did, _ = self._sync()                            # on it: left alone
        self.assertEqual((did, r.stdout), ([], ""))

    def test_its_own_network_is_taken_down_for_the_home_one(self):
        self._port("eth0", kind="1", carrier="0", device=True)     # no cable
        self._have("profile", "home", "answers", "radio", "up")
        _, did, state = self._sync()
        self.assertEqual(did, ["radio wifi on", "connection down aetherseed-hotspot",
                               "--wait 40 connection up aetherseed-home"])
        self.assertNotIn("up", state)

    def test_a_home_wifi_that_does_not_answer_brings_its_own_back(self):
        self._port("eth0", kind="1", carrier="0", device=True)     # no cable
        self._have("profile", "home")                       # wrong password, router off
        r, did, state = self._sync()
        self.assertEqual(did, ["radio wifi on", "--wait 40 connection up aetherseed-home",
                               "connection down aetherseed-home", "radio wifi on",
                               "connection up aetherseed-hotspot"])
        self.assertEqual(self._states(state), ["home", "profile", "radio", "up"])
        self.assertIn("did not answer", r.stderr)
        w = self._wifi_state()
        self.assertEqual((w.get("serving"), w.get("home_last")), ("own", "failed"))
        self.assertTrue(w.get("home_failed_at"))

    def test_after_a_failed_try_it_waits_before_trying_again(self):
        self._port("eth0", kind="1", carrier="0", device=True)     # no cable
        self._have("profile", "home")
        self._sync()
        self._have("answers")
        _, did, state = self._sync()                        # RETRY (300 s) has not passed
        self.assertEqual(did, [])
        self.assertIn("up", state)
        self.extra_env = {"AETHERSEED_HOME_RETRY": "0"}
        _, did, state = self._sync()                        # it has: tried, and joined
        self.assertIn("--wait 40 connection up aetherseed-home", did)
        self.assertIn("homeup", state)

    def test_never_while_a_phone_is_on_its_own_network(self):
        self._port("eth0", kind="1", carrier="0", device=True)     # no cable
        self._have("profile", "home")
        self._sync()
        self._have("answers", "phone")
        self.extra_env = {"AETHERSEED_HOME_RETRY": "0"}
        _, did, state = self._sync()
        self.assertEqual(did, [])                           # someone may be setting it up
        self.assertIn("up", state)

    def test_a_cable_takes_it_off_the_home_wifi(self):
        self._have("profile", "home", "radio", "homeup")
        self._port("eth0", kind="1", carrier="1", device=True)
        r, did, state = self._sync()
        self.assertEqual(did, ["connection down aetherseed-home", "radio wifi off"])
        self.assertEqual(self._states(state), ["home", "profile"])
        self.assertEqual(self._wifi_state().get("serving"), "cable")

    def test_a_unit_given_only_a_home_wifi_is_left_quiet_when_it_fails(self):
        self._port("eth0", kind="1", carrier="0", device=True)     # no cable
        self._have("home")                                  # no network of its own
        r, did, state = self._sync()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(did, ["radio wifi on", "--wait 40 connection up aetherseed-home",
                               "connection down aetherseed-home"])

    def test_setting_up_its_own_network_is_not_refused_for_the_home_one(self):
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "hotspot.sh")
        text = open(sh, encoding="utf-8").read()
        self.assertIn('grep -v "^$HOME_PROFILE:"', text)

    def test_watch_looks_again_on_a_clock_and_one_rule_runs_at_a_time(self):
        sh = os.path.join(os.path.dirname(SERVICES), "tools", "hotspot.sh")
        text = open(sh, encoding="utf-8").read()
        self.assertIn('while sleep "$TICK"; do sync_locked; done', text)
        self.assertIn("flock 9", text)


class NothingTheUnitStartsLeavesIt(unittest.TestCase):
    """. 

    Measured that day on a unit with a cable in: the kiosk's browser held a
    connection to Google, the clock was synced over the network, package lists
    were fetched daily, the unit announced itself - and the firewall's output
    chain was "policy accept".
    """

    def setUp(self):
        with open(os.path.join(SERVICES, "nftables.conf"), encoding="utf-8") as f:
            self.out = chain(directives(f.read()), "output")

    def test_outbound_is_dropped_unless_named(self):
        self.assertEqual(self.out[0], "type filter hook output priority filter; policy drop;")
        accepts = [l for l in self.out if l.endswith("accept")]
        # everything let out, line by line: a new one is added here on purpose
        self.assertEqual(accepts, [
            'oif "lo" accept',
            "ct state established,related accept",
            "udp sport 68 udp dport 67 accept",
            'oifname "wlan0" udp sport 67 udp dport 68 accept',
            # mDNS, 15 Nov 2026: to the link's multicast group, answers to the private ranges
            "udp dport 5353 ip daddr 224.0.0.251 accept",
            "udp dport 5353 ip6 daddr ff02::fb accept",
            "udp sport 5353 ip daddr @lan4 accept",
            "udp sport 5353 ip6 daddr @lan6 accept",
            # Claude with the owner's key, 21 Nov 2026: the companion's own process only
            'meta skuid "aetherseed" udp dport 53 accept',
            'meta skuid "aetherseed" tcp dport { 53, 443 } accept',
            # the clock from the network, 21 Nov 2026: the clock service's own user only
            'meta skuid "systemd-timesync" udp dport { 53, 123 } accept',
            'meta skuid "systemd-timesync" tcp dport 53 accept',
            "icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert, nd-router-solicit, "
            "mld-listener-report, mld2-listener-report } accept",
        ])

    def test_no_name_lookup_no_clock_no_web_is_let_out(self):
        # 21 Nov 2026: except, for Claude, the companion's own process
        # (user aetherseed): a name lookup and HTTPS. Nothing else on the unit.
        import re as _re
        others = " ".join(l for l in self.out if 'meta skuid "aetherseed"' not in l
                          and 'meta skuid "systemd-timesync"' not in l)
        for port in (r"dport 53\b", r"dport 123\b", r"dport 80\b", r"dport 443\b", r"\{ 53"):
            self.assertIsNone(_re.search(port, others), port)
        self.assertNotIn("ct state new", " ".join(self.out))
        self.assertNotIn("dport 80", " ".join(self.out))

    def test_what_tried_is_named_and_counted(self):
        self.assertEqual(self.out[-2],
                         'limit rate 6/minute log prefix "aetherseed out-drop: " flags skuid')
        self.assertEqual(self.out[-1], 'counter comment "outbound dropped by policy"')

    def test_the_browser_can_look_up_no_name(self):
        d = unit("aetherseed-kiosk.service")
        self.assertTrue(any("--host-resolver-rules='MAP * ~NOTFOUND , EXCLUDE 127.0.0.1'" in l
                            for l in d))
        self.assertTrue(any("--app=http://127.0.0.1:2077/" in l for l in d))

    def test_the_browser_may_open_the_console_and_nothing_else(self):
        import json
        with open(os.path.join(os.path.dirname(SERVICES), "kiosk", "chromium-policy.json"),
                  encoding="utf-8") as f:
            p = json.load(f)
        self.assertEqual(p["URLBlocklist"], ["*"])
        self.assertEqual(p["URLAllowlist"], ["127.0.0.1:2077"])
        for off in ("BackgroundModeEnabled", "MetricsReportingEnabled", "ComponentUpdatesEnabled",
                    "SearchSuggestEnabled", "TranslateEnabled", "PrintingEnabled",
                    "AllowFileSelectionDialogs", "BrowserNetworkTimeQueriesEnabled"):
            self.assertIs(p[off], False, off)
        self.assertIs(p["SyncDisabled"], True)
        self.assertEqual(p["DeveloperToolsAvailability"], 2)     # not available
        self.assertEqual(p["DownloadRestrictions"], 3)           # all blocked
        self.assertEqual(p["ExtensionInstallBlocklist"], ["*"])

    def test_the_clock_is_set_from_the_network(self):
        # 21 Nov 2026: "sync the clocks through the network on connection"
        with open(os.path.join(SERVICES, "timesyncd-aetherseed.conf"), encoding="utf-8") as f:
            d = directives(f.read())
        self.assertEqual(d, ["[Time]", "NTP=0.pool.ntp.org 1.pool.ntp.org 2.pool.ntp.org 3.pool.ntp.org",
                             "FallbackNTP=", "SaveIntervalSec=60"])
        inst = open(os.path.join(os.path.dirname(SERVICES), "install.sh"), encoding="utf-8").read()
        self.assertIn("/etc/systemd/timesyncd.conf.d/aetherseed.conf", inst)



if __name__ == "__main__":
    unittest.main()


class ANewUnitFromNothing(unittest.TestCase):
    """21 Nov 2026: a fresh Raspberry Pi OS image became a unit. What that
    took is in the repo now: the HailoRT tools, the screen freed from the
    desktop login, and the first start armed by the installer."""

    HERE = os.path.dirname(os.path.abspath(__file__))

    def read(self, *p):
        with open(os.path.join(self.HERE, *p), encoding="utf-8") as f:
            return f.read()

    def test_the_hailo_tools_are_valid_shell(self):
        import subprocess
        for f in ("build.sh", "install.sh", "check.sh"):
            with self.subTest(f=f):
                r = subprocess.run(["bash", "-n", os.path.join(self.HERE, "tools", "hailo", f)],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_download_is_checked(self):
        b = self.read("tools", "hailo", "build.sh")
        self.assertIn("-b \"v$V\"", b)                       # Hailo's sources at the tag
        self.assertIn("37899283", b)                         # firmware size
        self.assertIn("5656354387", b)                       # the 4B's size
        self.assertIn("aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4", b)
        self.assertIn("sha256sum -c", self.read("tools", "hailo", "install.sh"))

    def test_the_install_keeps_a_way_back_and_holds_the_companion(self):
        i = self.read("tools", "hailo", "install.sh")
        self.assertIn("hailo-files.tgz", i)
        self.assertIn("/var/cache/apt/archives/*hailo*.deb", i)
        self.assertIn("hailort-hold.conf", i)
        self.assertIn("hailort-hold.conf", self.read("tools", "hailo", "check.sh"))
        for pkg in ("h10-hailort", "python3-h10-hailort", "hailort", "hailo-gen-ai-model-zoo"):
            self.assertIn(pkg, i)

    def test_the_screen_is_the_companions(self):
        s = self.read("install.sh")
        self.assertIn("systemctl disable display-manager", s)
        self.assertIn("set-default multi-user.target", s)

    def test_the_first_start_is_armed_only_on_a_unit_nobody_has_set_up(self):
        s = self.read("install.sh")
        self.assertIn("--first-start", s)
        arm = s[s.index('if [ $FIRST = 1 ]'):]
        self.assertLess(arm.index("companion.json"), arm.index("touch /etc/aetherseed/first-start"))
        self.assertIn("hotspot.sh\" setup", arm)
