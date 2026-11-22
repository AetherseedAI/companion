#!/usr/bin/env python3
"""The Companion's GUI server.

Serves the console on port 2077 and reverse-proxies the node's API to the
proxy on 8001, so the browser only ever speaks to ONE origin. That is not
decoration: a page on :2077 calling :8001 is cross-origin, which would mean
either CORS headers on the guard layer or a browser that has to be told to
relax. Neither belongs on a device whose claim is that nothing leaves it.

It talks to 8001, never to hailo-ollama on 8000. Every guard - the token
budget, the sanitizers, all four generation bounds, provenance - lives at the
proxy's exit point, and a UI that went straight to the model would have none
of them.

Static files only, read-only, no directory listing. One write: the shutdown
request (see SHUTDOWN_REQUEST), an empty file that a root-owned systemd path
unit turns into an orderly poweroff. This server never gains the privilege to
shut anything down itself.

A document for the steward's own shelf passes THROUGH this
server and is never written by it: the upload is relayed to the proxy, which
keeps it under its own state directory (logic/own_shelf.py).

Who may use it: whoever is at the unit's own screen (the owner), and a
phone or laptop that has signed in - as the owner, or as a person the owner
added (gui/signin.py, gui/people.py). There is no guest: a device that has not
signed in is shown the page, who is here and the manual, and nothing of
anyone's; it cannot talk with her.
"""
import base64
import hashlib
import http.server
import json
import math
import os
import re
import socket
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import signin  # noqa: E402  (gui/signin.py, beside this file)
import people  # noqa: E402  (gui/people.py: more than one person, a root each)


def _manual_sections(lang):
    """gui/manual.<lang>.md as sections (logic/manual.py reads it the same
    way for her shelf). Loaded by path: this server imports nothing else of
    the application."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "aetherseed_manual", os.path.join(os.path.dirname(_HERE), "logic", "manual.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.sections(lang)

BIND = os.environ.get("AETHERSEED_GUI_BIND", "127.0.0.1")
PORT = int(os.environ.get("AETHERSEED_GUI_PORT", "2077"))
BACKEND = os.environ.get("AETHERSEED_BACKEND", "http://127.0.0.1:8001")
ROOT = os.path.dirname(os.path.abspath(__file__))

# Only these reach the backend. An allow-list rather than a prefix match, so a
# future route on the proxy is not exposed to the browser by accident.
# /aetherseed/steward: guided correction - the steward supports
# or corrects a turn or a ring. The console's only way to change what the
# companion remembers; the proxy checks and records every one.
PROXIED_POST = ("/api/chat", "/aetherseed/setup", "/aetherseed/steward",
                "/aetherseed/shelf/remove",
                # the steward's workspace editor (20 Oct 2026)
                "/aetherseed/workspace/save", "/aetherseed/workspace/mkdir",
                "/aetherseed/workspace/delete", "/aetherseed/workspace/rename",
                #the training loop's buttons, and who her steward is
                "/aetherseed/training", "/aetherseed/steward-name",
                #the steward's own training files
                "/aetherseed/training-file", "/aetherseed/training-file/remove",
                #the steward's brake; trust management
                "/aetherseed/brake", "/aetherseed/trust", "/aetherseed/approvals",
                #the COG panel. Not /aetherseed/cog/reflection
                # or /aetherseed/cog/remove: those are the harness's, by token.
                "/aetherseed/cog/start", "/aetherseed/cog/stop", "/aetherseed/cog/review",
                "/aetherseed/cog/correct", "/aetherseed/cog/reflect", "/aetherseed/cog/forget",
                # Claude with the owner's own key (logic/cloud.py)
                "/aetherseed/cloud")

# THE STEWARD'S OWN SHELF. : "a file upload
# button in the gui, that adds documents to the library/workspace". The body
# of the request is the file itself; its name is in X-Filename. Three checks
# here, before a byte is read: the size, the content type, and that the name
# header is there - a page on another origin cannot send a custom header
# without a preflight, and this server answers none. What the file is, the
# proxy decides (logic/own_shelf.accept).
UPLOAD_PATH = "/aetherseed/upload"
UPLOAD_MAX = int(os.environ.get("AETHERSEED_UPLOAD_MAX", str(60 * 1024 * 1024)))
UPLOAD_TYPE = "application/octet-stream"

# SHUTDOWN. So the device can be moved without pulling the plug on a running
# SQLite store. The console cannot power anything off - it runs unprivileged
# with NoNewPrivileges, and should stay that way. It only leaves a request in
# its own runtime directory; services/aetherseed-shutdown.path watches for it
# and starts a root oneshot that removes it and calls poweroff. /run is tmpfs,
# so a request can never survive into the next boot and shut it down again.
# Only this server can write there: the proxy (the model's side) runs with
# ProtectSystem=strict and no writable path under /run.
SHUTDOWN_PATH = "/aetherseed/shutdown"
SHUTDOWN_REQUEST = os.environ.get("AETHERSEED_SHUTDOWN_REQUEST",
                                  "/run/aetherseed-gui/shutdown-request")
SHUTDOWN_CONFIRM = "shut down"

# THE SERVED MODEL. The unit's own setting (/etc/aetherseed/model.env), and
# the owner's to change: one Hailo device holds one model, so it is the
# unit's, not a person's. This server changes nothing itself - as for a
# power-off it leaves a request in its runtime directory, here the model's
# NAME and nothing else, and services/aetherseed-model.path starts the root
# side (tools/model.py --request), which checks the name again against this
# build's models with a measured ceiling and a file in the store. What may be
# offered is read from a root-written list; a name not on it is refused here.
MODEL_PATH = "/aetherseed/model"
MODEL_REQUEST = os.environ.get("AETHERSEED_MODEL_REQUEST", "/run/aetherseed-gui/model-request")
MODEL_RESULT = os.environ.get("AETHERSEED_MODEL_RESULT", "/run/aetherseed-gui/model-result")
MODEL_CHOICES = os.environ.get("AETHERSEED_MODEL_CHOICES", "/etc/aetherseed/models.json")
MODEL_FILE = os.environ.get("AETHERSEED_MODEL_FILE", "/etc/aetherseed/model.env")
_MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,30}:[a-z0-9.\-]{1,12}$")


def model_choices():
    """[{name, ready, why_not}] as root last wrote it; [] when there is none."""
    try:
        with open(MODEL_CHOICES, encoding="utf-8") as f:
            d = json.load(f)
        return [m for m in d.get("models", [])
                if isinstance(m, dict) and isinstance(m.get("name"), str) and _MODEL_NAME.match(m["name"])]
    except (OSError, ValueError, AttributeError):
        return []


def model_setting():
    try:
        with open(MODEL_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("AETHERSEED_MODEL="):
                    return line.strip().split("=", 1)[1].strip("'\"") or None
    except OSError:
        pass
    return None


def model_result():
    try:
        with open(MODEL_RESULT, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None

# FIRST START. A unit that is onboarded where it will live is
# named there, and there it is also given the time and a passkey for its own
# Wi-Fi - by whoever sits at ITS OWN SCREEN, once. Both need root, so this
# server does with them what it does with a shutdown: it leaves a request in
# its runtime directory, and services/aetherseed-first-start.path starts a
# root oneshot (tools/first_start.sh) that does the two things and says how
# it went. Three locks, each checked here and again by the root side:
#   - the unit is ARMED: /etc/aetherseed/first-start exists (a card made a
#     source by tools/source_card.sh has it; the first start removes it). A
#     unit set up at a shell never has it, and this path then does nothing;
#   - the request comes from loopback - the unit's own screen. A phone can
#     only be on the unit's Wi-Fi once there is a passkey, so it cannot be
#     what sets one; and the console is not served on a cable network at all;
#   - what is asked is a date and time and a passkey, in their own shapes.
# The passkey is written to the request (tmpfs, mode 600), read by root and
# removed; it is never logged here and never sent back.
FIRST_START_PATH = "/aetherseed/first-start"
LOCK_PI_PATH = "/aetherseed/lock-pi"
LOCK_PI_REQUEST = os.environ.get("AETHERSEED_LOCK_PI_REQUEST", "/run/aetherseed-gui/lock-pi-request")
LOCK_PI_RESULT = os.environ.get("AETHERSEED_LOCK_PI_RESULT", "/run/aetherseed-gui/lock-pi-result")
LOCK_PI_WAIT = 40                  # su waits ~3 s after a wrong password
_LOCK_PI_LOCK = threading.Lock()

# A HOME WI-FI (16 Nov 2026: "The unit should be able to connect to the wifi
# regardless. it should broadcast its name secretly, and anyone who knows it
# can then connect it to a wifi"). Who may: the unit's own screen, a phone on
# the unit's own hidden network (knowing its name and passkey is the gate), or
# the steward signed in from anywhere. The console only passes the network on
# (a request file, mode 600); root's side (tools/wifi.py) saves it and
# tools/hotspot.sh joins it by its rule. The password is never logged.
WIFI_PATH = "/aetherseed/wifi"
WIFI_REQUEST = os.environ.get("AETHERSEED_WIFI_REQUEST", "/run/aetherseed-gui/wifi-request")
WIFI_RESULT = os.environ.get("AETHERSEED_WIFI_RESULT", "/run/aetherseed-gui/wifi-result")
WIFI_STATE = os.environ.get("AETHERSEED_WIFI_STATE", "/run/aetherseed-wifi-state")
WIFI_NAME = os.environ.get("AETHERSEED_WIFI_NAME", "/etc/aetherseed/wifi-home")
OWN_WIFI = os.environ.get("AETHERSEED_OWN_WIFI", "10.42.0.")       # the hidden network's addresses
WIFI_WAIT = 25                     # a scan takes some seconds
_WIFI_LOCK = threading.Lock()
_wifi_joins = []                   # monotonic times of joins asked for
_lock_pi_tries = []                # monotonic times of refused tries
# Names the admin account may not take (root's side also refuses any account
# the unit already has).
RESERVED_LOGINS = frozenset({"root", "pi", "admin", "aetherseed", "aetherseed-kiosk", "daemon",
                             "bin", "sys", "sync", "nobody", "systemd-network", "messagebus"})
FIRST_START_FLAG = os.environ.get("AETHERSEED_FIRST_START_FLAG", "/etc/aetherseed/first-start")
FIRST_START_REQUEST = os.environ.get("AETHERSEED_FIRST_START_REQUEST",
                                     "/run/aetherseed-gui/first-start-request")
FIRST_START_RESULT = os.environ.get("AETHERSEED_FIRST_START_RESULT",
                                    "/run/aetherseed-gui/first-start-result")
SETUP_KEY = os.environ.get("AETHERSEED_SETUP_KEY", "/etc/aetherseed/setup-wifi.key")
FIRST_START_WAIT = float(os.environ.get("AETHERSEED_FIRST_START_WAIT", "75"))
_WHEN = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])[T ]([01]\d|2[0-3]):([0-5]\d)$")
_FIRST_START_LOCK = threading.Lock()


def first_start_armed():
    return os.path.exists(FIRST_START_FLAG)


def check_when(when):
    """'YYYY-MM-DD HH:MM' if `when` is a date and time that exists, else None."""
    m = _WHEN.match(when if isinstance(when, str) else "")
    if not m:
        return None
    try:
        time.strptime("%s-%s-%s %s:%s" % m.groups(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None                         # the 31st of February
    return "%s-%s-%s %s:%s" % m.groups()


def check_passkey(key):
    """A WPA2 passkey: 8-63 printable ASCII characters (tools/hotspot.sh)."""
    return signin.passkey_shape_ok(key)


# ---- SIGNED IN, OR NOT ---------------------------------------------
# the steward signs in from a phone with "steward name + passkey". How, and
# what it does not protect against: gui/signin.py.
#
# NO GUEST. A device that is neither the unit's own screen nor signed in may
# load the page, ask who is here (WHOAMI_PATH), read the manual, be told the
# companion's name and language (status_before_sign_in) and sign in. It
# cannot talk with her, and nothing it sends reaches any proxy but that one
# status question. Everything else this server relays or does belongs to
# somebody signed in - her memory and records, corrections, trust, approvals,
# training, the COG panel, documents, the brake and quantum rest. the brake:
# "an authorized person should always be able to pause or shut down a model
# mid-task".
STEWARD_KEY = os.environ.get("AETHERSEED_STEWARD_KEY", "/etc/aetherseed/steward.key")
# ---- MORE THAN ONE PERSON (gui/people.py) ------------------------
# The OWNER is the steward of before: the unit's own screen, or a phone signed
# in with the steward key; the owner's requests go to BACKEND. A MEMBER is a
# person the owner added: signed in with a passkey of their own, set at their
# first sign-in; a member's requests go to that member's own proxy and to no
# other, so a member reads and changes only their own root. What is the
# unit's, not a root's, stays with the owner: OWNER_ONLY below, the power-off
# and the first start.
CLAIM_PATH = "/aetherseed/claim"        # a member's first sign-in: choose a passkey
OWNER_ONLY_POST = frozenset({
    "/aetherseed/setup", "/aetherseed/steward-name",          # the companion's name; who the steward is
    "/aetherseed/training", "/aetherseed/training-file", "/aetherseed/training-file/remove",
    "/aetherseed/brake", "/aetherseed/trust",                  # the brake; granting and lowering trust
    "/aetherseed/cog/start", "/aetherseed/cog/stop", "/aetherseed/cog/review",
    "/aetherseed/cog/correct", "/aetherseed/cog/reflect", "/aetherseed/cog/forget",
    "/aetherseed/cloud"})
OWNER_ONLY_GET = frozenset({"/aetherseed/training", "/aetherseed/cog", "/aetherseed/cog/essay"})
SIGNIN_PATH = "/aetherseed/steward-signin"
SIGNOUT_PATH = "/aetherseed/steward-signout"
WHOAMI_PATH = "/aetherseed/whoami"
MANUAL_PATH = "/aetherseed/manual"      #the Help panel's text
OWN_SCREEN = frozenset({"127.0.0.1", "::1"})     # the unit's own screen: loopback
OPEN_GET = frozenset({"/aetherseed/status", FIRST_START_PATH, WHOAMI_PATH})
# What a device that has not signed in is answered when it tries to talk.
SIGN_IN_TO_TALK = {"error": "Sign in to talk with me.", "code": "sign_in"}
SESSIONS = signin.Sessions()
LOCKOUT = signin.Lockout()


RELAY_BODY_MAX = 2 * 1024 * 1024       # the steward's JSON requests: a training file is 256 KB


def content_length(headers, limit):
    """The length of the body the client declared: a whole number from 0 to
    `limit`; None for anything else - not a number, negative (read(-1) reads
    until the connection closes), or too large."""
    raw = headers.get("Content-Length")
    if raw is None or not raw.strip():
        return 0
    try:
        n = int(raw.strip())
    except ValueError:
        return None
    return n if 0 <= n <= limit else None


def status_before_sign_in(d, owner=False):
    """What a device that has not signed in is told of the unit: what the
    who-is-here and sign-in screens need to show themselves - whether the
    companion has been named, her name and her language - and nothing else:
    not the model, her level, the brake, or any count, and not the steward's
    name either unless `owner` (a unit with people added: _status_before_sign_in)."""
    c = d.get("companion") if isinstance(d, dict) else None
    if not isinstance(c, dict):
        return {}
    keys = ("configured", "name", "language") + (("steward",) if owner else ())
    return {"companion": {k: c[k] for k in keys if k in c}}


# THE CONSOLE WAS SEEN. The page asks for /aetherseed/status every 15 seconds
# for as long as it is loaded, so "the browser is showing the console" has a
# cheap witness: this file's modification time, touched on every status poll.
# services/aetherseed-kiosk-watch.service reads it and restarts the screen when
# the browser has been up for a while and the page is not asking: a deployment unit showed a blank white page twice - the page
# load was cut off as the network came up under it, and a kiosk browser does
# not try again. tmpfs, in this server's own runtime directory, beside the
# shutdown request; it holds nothing but its timestamp.
CONSOLE_SEEN = os.environ.get("AETHERSEED_CONSOLE_SEEN",
                              "/run/aetherseed-gui/console-seen")


def _console_seen():
    try:
        with open(CONSOLE_SEEN, "a"):
            os.utime(CONSOLE_SEEN, None)
    except OSError:
        pass                        # a witness that cannot be written is not worth a crash


# /aetherseed/rings: the ring tree - read-only, like the record.
# /aetherseed/memories: the turns, for guided correction (50); it takes a query
# string (?before=&q=&limit=), so it is matched on its path alone.
# /aetherseed/shelf: the steward's own documents and how far each is read (62).
PROXIED_GET = ("/aetherseed/status", "/aetherseed/record", "/aetherseed/rings", "/api/tags",
               "/aetherseed/journal",          # her living journal, read-only
               "/aetherseed/shelf", "/aetherseed/training", "/aetherseed/trust-record",
               "/aetherseed/brake", "/aetherseed/trust",
               #her records checked; her workspace, read-only
               "/aetherseed/records", "/aetherseed/workspace", "/aetherseed/workspace/tree",
               "/aetherseed/approvals",
               #the conversation in progress, drawn again after a refresh -
               #the signed-in person's own proxy only (_backend)
               "/aetherseed/session",
               #the COG panel - its state, and one essay (?n=)
               "/aetherseed/cog")
PROXIED_GET_QUERY = ("/aetherseed/memories", "/aetherseed/cog/essay",
                     "/aetherseed/workspace/file")

# The page's own script is pinned by the hash of its bytes.
#
# The first version of this header said default-src 'self' and never said
# script-src at all, so default-src applied to scripts - and an inline
# <script> is not 'self'. Chromium refused the page's entire script on every
# load for as long as the console existed. HTML and CSS rendered, so it LOOKED
# like a working console; every endpoint had been tested with curl, which runs
# no JavaScript, and the page itself had never been opened in a browser.
#
# 'unsafe-inline' would fix it and say "any inline script may run here". A
# hash says "this one may". Anything else - a script injected into the DOM at
# runtime included - is refused. That is the same principle as pinning the
# model by the hash of its blob, applied to the one piece of code on this
# device that renders model output.
#
# The hash is taken from the file being served, so it is not protection
# against someone editing that file; the cartridge manifest is. It is computed
# once at startup, so if index.html changed underneath a running server the
# page would stop working rather than run something unpinned - it fails
# closed, which is the direction it should fail in.
def inline_hashes(html):
    """{'script': ["'sha256-...'", ...], 'style': [...]} for every inline block."""
    out = {}
    for tag in ("script", "style"):
        out[tag] = ["'sha256-%s'" % base64.b64encode(
            hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode()
            for m in re.finditer(r"<%s>(.*?)</%s>" % (tag, tag), html, re.S)]
    return out


def build_csp(html):
    h = inline_hashes(html)
    return ("default-src 'self'; "
            "script-src 'self' %s; "
            "style-src 'self' %s; "
            "img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            % (" ".join(h["script"]), " ".join(h["style"])))


CSP = None      # set in __main__, once index.html is known to exist


# How the console says it is alive when nobody is standing in front of it.
#
# A kiosk has no other way to report itself: the screen is the output, and
# if you cannot see the screen you cannot see the output. The page polls
# /aetherseed/status on a timer, so counting those polls answers the only
# question that matters remotely - is the browser still running the page, or
# is it showing a frozen picture of one.
#
# Counts, and nothing else. Not paths, not bodies, not prompts. A per-request
# log on this device would put everything anyone typed into the journal, and
# the journal is not covered by any promise this node makes.
HEARTBEAT_SECONDS = int(os.environ.get("AETHERSEED_GUI_HEARTBEAT", "300"))

_counts = {"page": 0, "status": 0, "record": 0, "rings": 0, "chat": 0, "setup": 0,
           "refused": 0, "upload": 0, "shelf": 0, "training": 0, "signin": 0}
_counts_lock = threading.Lock()


def _tally(kind):
    with _counts_lock:
        _counts[kind] = _counts.get(kind, 0) + 1


def _heartbeat():
    """One line per interval, always - including when idle.

    Silence has to mean "the server is gone", never "the server is quiet",
    or the heartbeat cannot be used to tell those two apart.
    """
    while True:
        time.sleep(HEARTBEAT_SECONDS)
        with _counts_lock:
            seen = dict(_counts)
            for k in _counts:
                _counts[k] = 0
        if sum(seen.values()):
            print("[gui] %ds  page=%d status=%d record=%d rings=%d chat=%d setup=%d "
                  "refused=%d upload=%d shelf=%d training=%d signin=%d"
                  % (HEARTBEAT_SECONDS, seen["page"], seen["status"],
                     seen["record"], seen["rings"], seen["chat"],
                     seen["setup"], seen["refused"], seen.get("upload", 0),
                     seen.get("shelf", 0), seen.get("training", 0),
                     seen.get("signin", 0)), flush=True)
        else:
            print("[gui] %ds  idle" % HEARTBEAT_SECONDS, flush=True)


# ---- ONLY REQUESTS ADDRESSED TO THE UNIT ----------------------
# A phone on the unit's own Wi-Fi often keeps its mobile data, and a web page it
# opens over that data can still send requests to http://10.42.0.1:2077. Two
# ways in, both found in this year's personal agents (OpenClaw CVE-2026-25253,
# Hermes Agent CVE-2026-53869, read):
#   - a CROSS-SITE request: the page posts to the console - a chat turn, an
#     approval, an upload - and the console cannot tell it from its own page.
#     The browser says where it came from in the Origin header;
#   - DNS REBINDING: a name the page controls is made to point at the unit, so
#     the browser counts the console as the page's own site and lets it read
#     the answers too. The Host header then carries that name, not the unit's.
# So: the Host must name the unit - localhost, its loopback address, or the
# address the request came in on - and a request that changes something and
# says where it came from must come from the console's own page. A request
# that says nothing (curl, the unit's own tools) is judged by its Host alone.
_LOCAL_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
EXTRA_HOSTS = frozenset(h.strip().lower() for h in
                        os.environ.get("AETHERSEED_CONSOLE_HOSTS", "").split(",") if h.strip())


def _own_names():
    """The unit's own name on the network: "<hostname>.local" (and the bare
    hostname). A .local name is answered by the unit itself on the local
    network (mDNS), not by any DNS server a web page could steer, so it is no
    door for rebinding. Read each time: the name can change at first start.
    (17 Nov 2026: http://<name>.local:2077 was refused as not_from_here.)"""
    try:
        h = socket.gethostname().strip().lower()
    except OSError:
        return set()
    return {h, h + ".local"} if h else set()


def _host_name(value: str) -> str:
    """The name in a Host header, lower-case, without its port."""
    v = (value or "").strip().lower()
    if v.startswith("["):                      # [::1]:2077
        return v[1:v.index("]")] if "]" in v else v
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


def addressed_here(host, origin, method, here, own_screen) -> bool:
    """ Is this request addressed to the unit itself and, if it
    changes something and a browser says where it comes from, from its page?"""
    if host is None:
        return own_screen                       # no Host at all: the unit's own only
    name = _host_name(host)
    if name not in _LOCAL_NAMES | EXTRA_HOSTS | {(here or "").lower()} | _own_names():
        return False
    if method in ("GET", "HEAD") or origin is None:
        return True
    if origin.strip().lower() in ("null", ""):
        return False
    return origin.strip().lower() == "http://" + host.strip().lower()


class Console(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass

    def _refused_if_not_from_here(self) -> bool:
        """True (and answered 403) when the request is not addressed to the unit."""
        try:
            here = self.connection.getsockname()[0]
        except (OSError, AttributeError, IndexError):
            here = ""
        if addressed_here(self.headers.get("Host"), self.headers.get("Origin"),
                          self.command, here, self._own_screen()):
            return False
        _tally("refused")
        print("[gui] refused a %s %s: Host %r, Origin %r - not addressed to this unit"
              % (self.command, self.path.split("?", 1)[0], self.headers.get("Host"),
                 self.headers.get("Origin")), flush=True)
        self._json(403, {"error": "This console answers only its own page on this unit.",
                         "code": "not_from_here"})
        return True

    def end_headers(self):
        # The page loads nothing from anywhere, and runs only its own script.
        # Saying so in a header means a mistake fails loudly instead of
        # silently reaching out - see build_csp.
        self.send_header("Content-Security-Policy", CSP)
        # Nothing this server sends is kept. Measured 2026-09-21: Chromium had
        # written the page and the status JSON to its disk cache, the page with
        # Last-Modified and no Cache-Control - which makes it heuristically
        # fresh, so after a new cartridge the kiosk could show the OLD console
        # without asking. And /aetherseed/record carries excerpts of flagged
        # prompts: cached, that is a second, unmanaged copy of what people
        # typed, on the SD card, outside everything the node accounts for.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _relay(self, method, body=None, headers=None, backend=None):
        req = urllib.request.Request(
            (backend or self._backend()) + self.path, data=body, method=method,
            headers=headers or {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as up:
                self.send_response(up.status)
                ctype = up.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ctype)
                self.end_headers()
                # Streamed straight through, unbuffered: the proxy already
                # decides what may be forwarded and when, and a
                # second layer of buffering here would undo the work that
                # makes the first token arrive when it does.
                while True:
                    chunk = up.read(1)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"error": "the node is not answering", "detail": repr(e)[:160]}
            ).encode())

    # ---- who is asking ----------------------------------------
    def _who(self):
        """Who this request is from: signin.OWNER (the unit's own screen, or a
        phone signed in with the steward key), a member (the dict of
        gui/people.py), or None - not signed in. A member the owner has since
        removed is nobody: the session names an id that is no longer there."""
        who = SESSIONS.who(signin.token_from_cookie(self.headers.get("Cookie")),
                           self.client_address[0])
        if who is not None and who != signin.OWNER:
            # a member, at a phone or - having signed in there - at the
            # unit's own screen, until they sign out
            member = people.by_id(people.load(), who)
            if member is not None:
                return member
            who = None
        if self._own_screen():
            return signin.OWNER
        if first_start_armed() and self._on_own_wifi():
            # Before the first start, a phone on the setup network sets the
            # unit up (21 Nov 2026: the first start "must be able to do it from
            # her phone"). The setup network's key is shown on the unit's own
            # screen only, so being on it means having stood at the unit.
            return signin.OWNER
        return who

    def _is_steward(self) -> bool:
        """Somebody with a root of their own here: the owner or a member."""
        return self._who() is not None

    def _is_owner(self) -> bool:
        return self._who() == signin.OWNER

    def _backend(self) -> str:
        """Whose proxy this request goes to: a member's own, else the unit's
        (the owner's)."""
        who = self._who()
        return people.backend(who) if isinstance(who, dict) else BACKEND

    def _owner_only(self) -> bool:
        """True (and answered) when this is not the owner: 401 when not signed in,
        403 for a member - signed in, but this is the unit's, not a root's."""
        who = self._who()
        if who == signin.OWNER:
            return False
        _tally("refused")
        if who is None:
            self._json(401, {"error": "Sign in as the steward to use this.", "code": "sign_in"})
        else:
            self._json(403, {"error": "Only this unit's owner can do that.", "code": "owner_only"})
        return True

    def _steward_only(self) -> bool:
        """True (and answered 401) when this is not the steward."""
        if self._is_steward():
            return False
        _tally("refused")
        self._json(401, {"error": "Sign in as the steward to use this.", "code": "sign_in"})
        return True

    def _manual(self):
        lang = "nb" if "lang=nb" in self.path else "en"
        try:
            sections = _manual_sections(lang)
        except OSError:
            self._json(404, {"error": "no manual on this unit"})
            return
        self._json(200, {"lang": lang, "sections": sections})

    def _whoami(self):
        # "key" says which passkey a phone signs in with - the Wi-Fi's, or one
        # of the steward's own (tools/steward_key.py) - so the page can name it
        # "person": whose root this request reaches; "people": the names a
        # sign-in page may offer, and which of them nobody has claimed yet
        own = self._own_screen()
        rec = None if own else signin.load_record(STEWARD_KEY)
        who = self._who()
        person = ({"role": "owner"} if who == signin.OWNER
                  else {"role": "member", "name": who["name"]} if isinstance(who, dict) else None)
        self._json(200, {"steward": who is not None, "own_screen": own,
                         "sign_in": rec is not None, "key": rec["source"] if rec else None,
                         "person": person, "people": people.public(people.load())})

    def _status_before_sign_in(self):
        _tally("status")
        try:
            with urllib.request.urlopen(BACKEND + "/aetherseed/status", timeout=10) as up:
                d = json.loads(up.read(262144))
        except Exception as e:
            self._json(502, {"error": "the node is not answering", "detail": repr(e)[:160]})
            return
        # on a unit with people added, their names are on the who-is-here
        # screen, and the owner's is told with them; a unit with one person
        # tells a device that has not signed in no name at all
        self._json(200, status_before_sign_in(d, owner=bool(people.load())))

    def _steward_name(self):
        """(the steward's name or None, whether the proxy answered at all)."""
        try:
            with urllib.request.urlopen(BACKEND + "/aetherseed/status", timeout=10) as up:
                d = json.loads(up.read(262144))
        except Exception:
            return None, False
        c = d.get("companion") if isinstance(d, dict) else None
        name = c.get("steward") if isinstance(c, dict) else None
        return (name if isinstance(name, str) and name.strip() else None), True

    def _sign_in(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 4096)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not a sign-in", "code": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        addr = self.client_address[0]
        if self._own_screen() and people.find(people.load(), data.get("name")) is None:
            self._json(200, {"steward": True, "own_screen": True})   # nothing to sign in to
            return
        wait = LOCKOUT.wait(addr)
        if wait > 0:
            self._json(429, {"error": "Too many tries. Wait, then try again.", "code": "locked",
                             "wait_s": int(math.ceil(wait))})
            return
        member = people.find(people.load(), data.get("name"))
        if member is not None:
            self._member_sign_in(member, data.get("passkey"), addr)
            return
        rec = signin.load_record(STEWARD_KEY)
        if rec is None:
            self._json(503, {"error": "Signing in as the steward is not set up on this unit.",
                             "code": "no_key"})
            return
        steward_name, answered = self._steward_name()
        if not answered:
            self._json(502, {"error": "the node is not answering", "code": "network"})
            return
        if not steward_name:
            self._json(409, {"error": "This unit has no steward's name yet.", "code": "no_steward_name"})
            return
        # Both are checked every time, whichever is wrong, and the answer does
        # not say which. The passkey is not kept, logged or sent back.
        key_ok = signin.passkey_matches(rec, data.get("passkey"))
        name_ok = signin.names_match(data.get("name"), steward_name)
        del data
        if not (key_ok and name_ok):
            LOCKOUT.failed(addr)
            print("[gui] a steward sign-in from %s did not match" % addr, flush=True)
            self._json(401, {"error": "That name and passkey do not match.", "code": "wrong"})
            return
        LOCKOUT.succeeded(addr)
        token = SESSIONS.open(addr)
        print("[gui] the steward signed in from %s" % addr, flush=True)
        self._json(200, {"steward": True, "own_screen": False},
                   headers={"Set-Cookie": signin.set_cookie(token)})

    def _member_sign_in(self, member, passkey, addr):
        """A member signs in with their own passkey. A name nobody has claimed
        yet has none: the page is told so (first_time) and asks for one to be
        chosen (CLAIM_PATH). A wrong passkey counts toward the lockout."""
        if not people.has_key(member["id"]):
            self._json(409, {"error": "Nobody has signed in as %s yet. Choose a passkey."
                             % member["name"], "code": "first_time", "name": member["name"]})
            return
        if not people.check(member["id"], passkey):
            LOCKOUT.failed(addr)
            print("[gui] a sign-in from %s did not match" % addr, flush=True)
            self._json(401, {"error": "That name and passkey do not match.", "code": "wrong"})
            return
        LOCKOUT.succeeded(addr)
        token = SESSIONS.open(addr, member["id"])
        print("[gui] %s signed in from %s" % (member["id"], addr), flush=True)
        self._json(200, {"steward": True, "own_screen": False,
                         "person": {"role": "member", "name": member["name"]}},
                   headers={"Set-Cookie": signin.set_cookie(token)})

    def _claim(self):
        """A member's first sign-in: {"name", "passkey"} sets that name's
        passkey - once. Whoever is first becomes that person here; the owner
        can take it away again (tools/people.py reset). Counted against the
        lockout like a sign-in, so a name cannot be tried for at speed."""
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 4096)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not a sign-in", "code": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        addr = self.client_address[0]
        wait = LOCKOUT.wait(addr)
        if wait > 0:
            self._json(429, {"error": "Too many tries. Wait, then try again.", "code": "locked",
                             "wait_s": int(math.ceil(wait))})
            return
        member = people.find(people.load(), data.get("name"))
        if member is None:
            LOCKOUT.failed(addr)
            self._json(404, {"error": "Nobody of that name has been added here.", "code": "no_such"})
            return
        outcome = people.claim(member["id"], data.get("passkey"))
        del data
        if outcome == "bad_passkey":
            self._json(400, {"error": "A passkey is 8 to 63 plain characters.", "code": "bad_passkey"})
            return
        if outcome == "taken":
            LOCKOUT.failed(addr)
            self._json(409, {"error": "%s already has a passkey. Sign in with it, or ask the "
                             "owner to reset it." % member["name"], "code": "taken"})
            return
        LOCKOUT.succeeded(addr)
        token = SESSIONS.open(addr, member["id"])
        print("[gui] %s chose a passkey and signed in from %s" % (member["id"], addr), flush=True)
        self._json(200, {"steward": True, "own_screen": False,
                         "person": {"role": "member", "name": member["name"]}},
                   headers={"Set-Cookie": signin.set_cookie(token)})

    def _brake_everyone(self, body):
        """The owner's brake is the unit's: after the owner's own proxy has
        taken it, each member's proxy is told the same, so a turn of anyone's
        stops and no new one starts. A member's proxy that does not answer is
        said in the log; it keeps what it last had."""
        for member in people.load():
            try:
                req = urllib.request.Request(people.backend(member) + "/aetherseed/brake", data=body,
                                             method="POST", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as up:
                    up.read(4096)
            except Exception as e:
                print("[gui] the brake did not reach %s: %r" % (member["id"], e), flush=True)

    def _sign_out(self):
        token = signin.token_from_cookie(self.headers.get("Cookie"))
        if token and SESSIONS.valid(token, self.client_address[0]):
            print("[gui] the steward signed out from %s" % self.client_address[0], flush=True)
        if token:
            SESSIONS.close(token)
        own = self._own_screen()
        self._json(200, {"steward": own, "own_screen": own},
                   headers={"Set-Cookie": signin.clear_cookie()})

    def do_GET(self):
        if self._refused_if_not_from_here():
            return
        if self.path == WHOAMI_PATH:
            _tally("status")
            self._whoami()
            return
        if self.path == MODEL_PATH:
            if self._owner_only():
                return
            _tally("status")
            self._model_state()
            return
        if self.path.split("?", 1)[0] == MANUAL_PATH:
            # The manual: for anybody at the console, signed in
            # or not - it is how to use her, nothing of anyone's.
            _tally("page")
            self._manual()
            return
        if self.path.split("?", 1)[0] in PROXIED_GET_QUERY:
            if self.path.split("?", 1)[0] in OWNER_ONLY_GET:
                if self._owner_only():
                    return
            elif self._steward_only():
                return
            _tally("memories" if self.path.startswith("/aetherseed/memories")
                   else "shelf" if self.path.startswith("/aetherseed/workspace") else "cog")
            self._relay("GET")
            return
        if self.path in PROXIED_GET:
            if self.path in OWNER_ONLY_GET:
                if self._owner_only():
                    return
            elif self.path not in OPEN_GET and self._steward_only():
                return
            # Only the unit's own screen is the witness: a phone on the
            # unit's Wi-Fi polls too, and its polls must not
            # hide a blank page on the screen from the kiosk watch.
            if self.path == "/aetherseed/status" and self._own_screen():
                _console_seen()
            if self.path == "/aetherseed/status" and not self._is_steward():
                self._status_before_sign_in()
                return
            _tally("status" if self.path.endswith("/status")
                   else "record" if self.path.endswith("/record")
                   else "rings" if self.path.endswith("/rings")
                   else "shelf" if self.path.endswith("/shelf")
                   else "training" if self.path.endswith("/training")
                   else "record" if self.path.endswith("/trust-record")
                   else "cog" if self.path == "/aetherseed/cog" else "page")
            self._relay("GET")
            return
        if self.path == FIRST_START_PATH:
            _tally("status")
            self._first_start_state()
            return
        if self.path == WIFI_PATH:
            _tally("status")
            self._wifi_state()
            return
        if self.path == "/":
            self.path = "/index.html"
        if self.path not in ("/index.html",):
            _tally("refused")
            self.send_error(404)
            return
        _tally("page")
        super().do_GET()

    def _json(self, code, obj, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _shutdown(self):
        # From the steward's screens. : "I
        # need a way to initiate quantum rest from the phone or laptop". Step
        # 54 had it at the unit only. Until any phone on the
        # unit's own Wi-Fi could ask for it; now a phone must be signed in as
        # the steward (do_POST checks before this is reached). Nothing else
        # reaches this server: the firewall admits the console port on
        # loopback and on the unit's own Wi-Fi, not on a cable network
        # (services/nftables.conf).
        # JSON with an explicit confirmation: a stray form post or a link cannot
        # send a JSON content type cross-origin without a preflight.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 4096)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not confirmed"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not isinstance(data, dict) or data.get("confirm") != SHUTDOWN_CONFIRM:
            self._json(400, {"error": "not confirmed"})
            return
        try:
            with open(SHUTDOWN_REQUEST, "w") as f:
                f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n")
        except OSError as e:
            print(f"[gui] shutdown requested but could not be filed: {e!r}", flush=True)
            self._json(503, {"error": "shutdown is not available on this unit"})
            return
        print("[gui] shutdown requested from %s" % ("the unit's own screen" if self._own_screen()
              else "the steward's phone on the unit's Wi-Fi"), flush=True)
        self._json(202, {"shutting_down": True})

    def _model_state(self):
        self._json(200, {"model": model_setting(), "models": model_choices(),
                         "switching": os.path.exists(MODEL_REQUEST), "last": model_result()})

    def _model_switch(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 4096)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not a model", "code": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        name = data.get("model") if isinstance(data, dict) else None
        ready = {m["name"] for m in model_choices() if m.get("ready")}
        if not isinstance(name, str) or name not in ready:
            self._json(400, {"error": "This unit cannot serve that model.", "code": "not_ready"})
            return
        if name == model_setting():
            self._json(200, {"model": name, "switching": False})
            return
        try:
            os.unlink(MODEL_RESULT)
        except OSError:
            pass
        try:
            fd = os.open(MODEL_REQUEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w") as f:
                f.write(name + "\n")
        except FileExistsError:
            self._json(409, {"error": "A switch is already under way.", "code": "busy"})
            return
        except OSError as e:
            print(f"[gui] a model switch was asked for but could not be filed: {e!r}", flush=True)
            self._json(503, {"error": "Switching the model is not available on this unit.",
                             "code": "unavailable"})
            return
        print(f"[gui] the owner asked for the model {name}", flush=True)
        self._json(202, {"model": name, "switching": True})

    def _own_screen(self):
        return self.client_address[0] in OWN_SCREEN

    def _on_own_wifi(self):
        return self.client_address[0].startswith(OWN_WIFI)

    def _may_set_wifi(self):
        return self._own_screen() or self._on_own_wifi() or self._is_steward()

    def _wifi_state(self):
        if not self._may_set_wifi():
            self._json(403, {"error": "Only at the unit, on its own Wi-Fi, or as the steward.",
                             "code": "not_here"})
            return
        state = {}
        try:
            with open(WIFI_STATE, encoding="utf-8") as f:
                for line in f:
                    k, _, v = line.rstrip("\n").partition("=")
                    if k in ("serving", "home_last"):
                        state[k] = v
        except OSError:
            pass
        try:
            with open(WIFI_NAME, encoding="utf-8") as f:
                name = f.readline(200).rstrip("\n")
        except OSError:
            name = ""
        self._json(200, {"serving": state.get("serving") or "",
                         "home": name, "home_last": state.get("home_last") or "",
                         "may_forget": self._own_screen() or self._is_steward()})

    def _wifi(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 1024)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not a request", "code": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not self._may_set_wifi():
            self._json(403, {"error": "Only at the unit, on its own Wi-Fi, or as the steward.",
                             "code": "not_here"})
            return
        action = data.get("action") if isinstance(data, dict) else None
        if action not in ("scan", "join", "forget"):
            self._json(400, {"error": "not a request", "code": "bad_request"})
            return
        req = {"action": action}
        if action == "forget" and not (self._own_screen() or self._is_steward()):
            self._json(403, {"error": "The steward forgets a network.", "code": "steward_only"})
            return
        if action == "join":
            ssid, pw = data.get("ssid"), data.get("password", "")
            if not (isinstance(ssid, str) and 1 <= len(ssid.encode("utf-8")) <= 32 and ssid.isprintable()):
                self._json(400, {"error": "Not a network name.", "code": "bad_ssid"})
                return
            if not (isinstance(pw, str) and (pw == "" or re.fullmatch(r"[ -~]{8,63}", pw)
                                             or re.fullmatch(r"[0-9a-fA-F]{64}", pw))):
                self._json(400, {"error": "A Wi-Fi password has 8 to 63 characters.",
                                 "code": "bad_password"})
                return
            now = time.monotonic()
            _wifi_joins[:] = [t for t in _wifi_joins if now - t < 3600]
            if len(_wifi_joins) >= 10:
                self._json(429, {"error": "Too many tries. Wait an hour.", "code": "too_many"})
                return
            _wifi_joins.append(now)
            req.update(ssid=ssid, password=pw)
        if not _WIFI_LOCK.acquire(blocking=False):
            self._json(409, {"error": "Already busy with the Wi-Fi.", "code": "busy"})
            return
        try:
            try:
                os.unlink(WIFI_RESULT)
            except OSError:
                pass
            try:
                fd = os.open(WIFI_REQUEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(req, f)
            except OSError as e:
                print(f"[gui] a Wi-Fi request could not be filed: {e!r}", flush=True)
                self._json(503, {"error": "Not available on this unit.", "code": "unavailable"})
                return
            req.pop("password", None)
            print(f"[gui] Wi-Fi: {action} asked for", flush=True)
            deadline = time.monotonic() + WIFI_WAIT
            res = None
            while time.monotonic() < deadline:
                try:
                    with open(WIFI_RESULT, encoding="utf-8") as f:
                        res = json.load(f)
                    break
                except (OSError, ValueError):
                    time.sleep(0.25)
            if res is None:
                try:
                    os.unlink(WIFI_REQUEST)            # no password left lying in /run
                except OSError:
                    pass
                self._json(504, {"error": "The unit did not answer. Try again.", "code": "timeout"})
                return
            if not isinstance(res, dict):
                res = {"ok": False, "code": "refused", "error": "It could not be done."}
            self._json(200 if res.get("ok") else 422, res)
        finally:
            _WIFI_LOCK.release()

    def _first_start_state(self):
        # What the page needs to decide whether to show the first-start step:
        # is this unit armed for it, is this screen the unit's own, and what
        # the unit's clock says now (to start the date and time fields from).
        armed, own = first_start_armed(), self._own_screen()
        out = {"armed": armed, "own_screen": own, "now": time.strftime("%Y-%m-%dT%H:%M"),
               "from_phone": armed and self._on_own_wifi()}
        if armed and own:
            # the setup network's name and key, for the unit's own screen only
            try:
                with open(SETUP_KEY, encoding="utf-8") as f:
                    k = f.read(64).strip()
                if re.fullmatch(r"[a-z0-9]{8,63}", k):
                    out["setup"] = {"ssid": "AetherSeed", "key": k, "address": "http://10.42.0.1:2077"}
            except OSError:
                pass
        self._json(200, out)

    def _lock_pi(self):
        """The onboarding's last button: lock the image's pi account once the
        admin's password is shown to work. The console only passes the
        password on (a request file, mode 600, in its runtime folder); root's
        side (tools/lock_pi_request.py) checks it the way a sign-in does and
        locks pi. Own screen only, 5 refused tries an hour, never logged."""
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 1024)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not a request", "code": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not self._own_screen():
            self._json(403, {"error": "pi is locked from the unit's own screen.", "code": "not_own_screen"})
            return
        pw = data.get("admin_password") if isinstance(data, dict) else None
        if not (isinstance(pw, str) and re.fullmatch(r"[ -~]{12,128}", pw)):
            self._json(400, {"error": "Type the admin password.", "code": "bad_admin_password"})
            return
        now = time.monotonic()
        _lock_pi_tries[:] = [t for t in _lock_pi_tries if now - t < 3600]
        if len(_lock_pi_tries) >= 5:
            self._json(429, {"error": "Too many tries. Wait an hour.", "code": "too_many"})
            return
        if not _LOCK_PI_LOCK.acquire(blocking=False):
            self._json(409, {"error": "Already being checked.", "code": "busy"})
            return
        try:
            for path in (LOCK_PI_RESULT,):
                try:
                    os.unlink(path)
                except OSError:
                    pass
            try:
                fd = os.open(LOCK_PI_REQUEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(pw + "\n")
            except OSError as e:
                print(f"[gui] lock pi asked for but could not be filed: {e!r}", flush=True)
                self._json(503, {"error": "Not available on this unit.", "code": "unavailable"})
                return
            del pw
            print("[gui] lock pi asked for at the unit's own screen", flush=True)
            deadline = time.monotonic() + LOCK_PI_WAIT
            lines = None
            while time.monotonic() < deadline:
                try:
                    with open(LOCK_PI_RESULT, encoding="utf-8") as f:
                        lines = f.read().split("\n")
                    break
                except OSError:
                    time.sleep(0.25)
            if lines is None:
                try:
                    os.unlink(LOCK_PI_REQUEST)         # no password left lying in /run
                except OSError:
                    pass
                self._json(504, {"error": "The unit did not answer. Try again.", "code": "timeout"})
                return
            if lines[0] == "ok":
                print(f"[gui] pi: {lines[1] if len(lines) > 1 else 'locked'}", flush=True)
                self._json(200, {"ok": True, "state": lines[1] if len(lines) > 1 else "locked"})
            else:
                code = lines[1] if len(lines) > 1 and re.fullmatch(r"[a-z_]{1,24}", lines[1]) else "refused"
                if code == "wrong_password":
                    _lock_pi_tries.append(time.monotonic())
                said = lines[2] if len(lines) > 2 and lines[2] else "It could not be done."
                print(f"[gui] lock pi refused: {code}", flush=True)
                self._json(422, {"error": said, "code": code})
        finally:
            _LOCK_PI_LOCK.release()

    def _first_start(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(415, {"error": "expected application/json"})
            return
        n = content_length(self.headers, 4096)
        if n is None:
            self.close_connection = True
            self._json(400, {"error": "not a first start", "code": "bad_request"})
            return
        try:
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if not (self._own_screen() or (first_start_armed() and self._on_own_wifi())):
            self._json(403, {"error": "A unit is started for the first time at its own screen "
                                      "or from a phone on its setup network.",
                             "code": "not_own_screen"})
            return
        if not first_start_armed():
            self._json(409, {"error": "This unit has been started before.", "code": "not_armed"})
            return
        when = check_when(data.get("when"))
        if not when:
            self._json(400, {"error": "That is not a date and time I can set.", "code": "bad_when"})
            return
        net = data.get("network", "hidden")
        if net not in ("hidden", "visible", "lan"):
            self._json(400, {"error": "Choose hidden, visible or none for the unit's own Wi-Fi.",
                             "code": "bad_network"})
            return
        key = data.get("passkey")
        if net == "lan" and not key:
            key = ""
        elif not check_passkey(key):
            self._json(400, {"error": "The passkey must be 8 to 63 plain characters.",
                             "code": "bad_passkey"})
            return
        # The steward's own passkey:
        # not the Wi-Fi passkey, which everyone given the Wi-Fi holds.
        own = data.get("steward_passkey")
        if not check_passkey(own):
            self._json(400, {"error": "Your own passkey must be 8 to 63 plain characters.",
                             "code": "bad_steward_key"})
            return
        if key and own == key:
            self._json(400, {"error": "Your own passkey must not be the Wi-Fi passkey.",
                             "code": "same_key"})
            return
        # The unit's admin account (tools/first_start.sh makes it): a login
        # name of the owner's choosing and a password of 12 or more.
        admin = data.get("admin_name")
        if not (isinstance(admin, str) and re.fullmatch(r"[a-z][a-z0-9_-]{1,30}", admin)):
            self._json(400, {"error": "The admin name must be 2 to 31 small letters, digits, - or _, "
                                      "starting with a letter.", "code": "bad_admin_name"})
            return
        if admin in RESERVED_LOGINS:
            self._json(400, {"error": "That name is already an account on this unit. Choose another.",
                             "code": "admin_taken"})
            return
        apw = data.get("admin_password")
        if not (isinstance(apw, str) and re.fullmatch(r"[ -~]{12,128}", apw)):
            self._json(400, {"error": "The admin password must be 12 to 128 plain characters.",
                             "code": "bad_admin_password"})
            return
        if apw == own or (key and apw == key):
            self._json(400, {"error": "The admin password must not be either passkey.",
                             "code": "same_admin_password"})
            return
        if not _FIRST_START_LOCK.acquire(blocking=False):
            self._json(409, {"error": "A first start is already under way.", "code": "busy"})
            return
        try:
            try:
                os.unlink(FIRST_START_RESULT)
            except OSError:
                pass
            try:
                fd = os.open(FIRST_START_REQUEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(when + "\n" + key + "\n" + own + "\n" + admin + "\n" + apw + "\n" + net + "\n")
            except OSError as e:
                print(f"[gui] first start asked for but could not be filed: {e!r}", flush=True)
                self._json(503, {"error": "The first start is not available on this unit.",
                                 "code": "unavailable"})
                return
            del key, own, apw
            print("[gui] first start asked for at the unit's own screen", flush=True)
            deadline = time.monotonic() + FIRST_START_WAIT
            lines = None
            while time.monotonic() < deadline:
                try:
                    with open(FIRST_START_RESULT, encoding="utf-8") as f:
                        lines = f.read().split("\n")
                    break
                except OSError:
                    time.sleep(0.25)
            if lines is None:
                # Nobody took it: do not leave a passkey lying in /run.
                try:
                    os.unlink(FIRST_START_REQUEST)
                except OSError:
                    pass
                self._json(504, {"error": "The unit did not answer. Try again.", "code": "timeout"})
                return
            if lines[0] == "ok":
                print("[gui] first start done", flush=True)
                self._json(200, {"ok": True, "network": lines[1] if len(lines) > 1 else "",
                                 "host": lines[2] if len(lines) > 2 else "",
                                 "mode": (lines[3] if len(lines) > 3 else "") or "hidden"})
            else:
                # root's side: "error", a word the page has a sentence for in
                # each language, and root's own sentence
                code = lines[1] if len(lines) > 1 and re.fullmatch(r"[a-z_]{1,24}", lines[1]) else "refused"
                said = lines[2] if len(lines) > 2 and lines[2] else "It could not be done."
                print(f"[gui] first start refused: {said}", flush=True)
                self._json(422, {"error": said, "code": code})
        finally:
            _FIRST_START_LOCK.release()

    def _upload(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        name = self.headers.get("X-Filename") or ""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if n > UPLOAD_MAX:
            # Refused unread: the rest of the request is not taken in.
            self.close_connection = True
            _tally("refused")
            self._json(413, {"error": "That file is too large: %d MB is the most I take."
                             % (UPLOAD_MAX // (1024 * 1024)), "code": "too_large"})
            return
        if n <= 0 or ctype != UPLOAD_TYPE or not name or len(name) > 800 \
                or not re.fullmatch(r"[A-Za-z0-9._~%!'()*-]+", name):
            self.close_connection = True
            _tally("refused")
            self._json(400, {"error": "not an upload from the console", "code": "bad_upload"})
            return
        _tally("upload")
        self._relay("POST", self.rfile.read(n),
                    headers={"Content-Type": UPLOAD_TYPE, "X-Filename": name})

    def do_POST(self):
        if self._refused_if_not_from_here():
            return
        if self.path == SIGNIN_PATH:
            _tally("signin")
            self._sign_in()
            return
        if self.path == SIGNOUT_PATH:
            _tally("signin")
            self._sign_out()
            return
        if self.path == CLAIM_PATH:
            _tally("signin")
            self._claim()
            return
        if self.path == SHUTDOWN_PATH:
            if self._owner_only():
                return
            self._shutdown()
            return
        if self.path == MODEL_PATH:
            if self._owner_only():
                return
            _tally("setup")
            self._model_switch()
            return
        if self.path == FIRST_START_PATH:
            # the unit's own screen only - checked in _first_start - and the
            # unit's own screen is the steward
            _tally("setup")
            self._first_start()
            return
        if self.path == WIFI_PATH:
            # own screen, the unit's own Wi-Fi, or the steward: checked in _wifi
            _tally("setup")
            self._wifi()
            return
        if self.path == LOCK_PI_PATH:
            # the unit's own screen only, checked in _lock_pi
            _tally("setup")
            self._lock_pi()
            return
        if self.path == UPLOAD_PATH:
            if self._steward_only():
                return
            self._upload()
            return
        if self.path not in PROXIED_POST:
            _tally("refused")
            self.send_error(404)
            return
        if self.path == "/api/chat" and not self._is_steward():
            # no guest: nobody talks with her without signing in, and the
            # turn is not read, let alone passed on
            _tally("refused")
            self.close_connection = True
            self._json(401, SIGN_IN_TO_TALK)
            return
        if self.path in OWNER_ONLY_POST:
            if self._owner_only():
                return
        elif self._steward_only():
            return
        _tally("setup" if self.path == "/aetherseed/setup"
               else "steward" if self.path in ("/aetherseed/steward", "/aetherseed/steward-name")
               else "training" if self.path == "/aetherseed/training"
               else "shelf" if self.path.startswith(("/aetherseed/shelf", "/aetherseed/workspace"))
               else "cog" if self.path.startswith("/aetherseed/cog/") else "chat")
        n = content_length(self.headers, RELAY_BODY_MAX)
        if n is None:
            self.close_connection = True
            _tally("refused")
            self._json(413, {"error": "That request is too large.", "code": "too_large"})
            return
        body = self.rfile.read(n) if n else b""
        if self.path == "/aetherseed/cloud" and b'"key"' in body \
                and not (self._own_screen() or self._on_own_wifi()):
            # The Anthropic key crosses no network but the unit's own: typed
            # at its screen, or from a phone on its WPA2 Wi-Fi. The console on
            # the home network is plain HTTP.
            try:
                is_key = json.loads(body).get("action") == "key"
            except Exception:
                is_key = True
            if is_key:
                self._json(403, {"error": "The key is set at the unit's own screen or from its own Wi-Fi.",
                                 "code": "key_on_unit_only"})
                return
        self._relay("POST", body)
        if self.path == "/aetherseed/brake":
            self._brake_everyone(body)


class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"[gui] console on http://{BIND}:{PORT}  ->  {BACKEND}", flush=True)
    if not os.path.exists(os.path.join(ROOT, "index.html")):
        print("[gui] FATAL: index.html is missing next to serve.py", flush=True)
        sys.exit(1)
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        CSP = build_csp(f.read())
    print("[gui] script pinned: %s" % " ".join(inline_hashes(
        open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())["script"]),
        flush=True)
    threading.Thread(target=_heartbeat, daemon=True).start()
    Threaded((BIND, PORT), Console).serve_forever()
