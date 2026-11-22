#!/usr/bin/env python3
"""The people who have a root of their own on this unit (gui/people.py).

The unit's owner is the steward named at first start. The owner can add
people; each gets a root of their own - memory, facts, rings, shelf, notes,
record, trust standing - served by a proxy of their own, and chooses a
passkey at their first sign-in.

    sudo tools/people.py add NAME       a new person: their root, their proxy
         tools/people.py list           who is here, and who has yet to sign in
    sudo tools/people.py reset NAME     take their passkey away: the next sign-in
                                        under that name chooses a new one. Their
                                        root is not touched.
    sudo tools/people.py remove NAME    stop their proxy and take the name off the
                                        sign-in page. Their root is kept, moved
                                        aside under a dated name; delete it
                                        yourself when you are sure.

Until a name's first sign-in, anyone who can reach the console can claim it:
add a person when they are about to sign in, and `reset` if the wrong one did.
"""
import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from gui import people  # noqa: E402
from logic import companion  # noqa: E402

OWNER_HOME = os.environ.get("AETHERSEED_OWNER_HOME", "/var/lib/aetherseed")
ENV_DIR = os.environ.get("AETHERSEED_PEOPLE_ENV", "/etc/aetherseed/people")
SERVICE_USER = os.environ.get("AETHERSEED_USER", "aetherseed")
SYSTEMCTL = os.environ.get("AETHERSEED_SYSTEMCTL", "systemctl")     # "" = leave the services alone (tests)


def _say(msg):
    print("people: " + msg)


def _owner_settings():
    return companion.load(os.path.join(OWNER_HOME, ".aetherseed", "companion.json")) or {}


def _chown(path):
    try:
        u = pwd.getpwnam(SERVICE_USER)
        for root, dirs, files in os.walk(path):
            os.chown(root, u.pw_uid, u.pw_gid)
            for f in files:
                os.chown(os.path.join(root, f), u.pw_uid, u.pw_gid)
    except (KeyError, PermissionError):
        pass                                     # a test, or not root: said by the caller's checks


def _systemctl(*args) -> bool:
    if not SYSTEMCTL:
        return True
    return subprocess.run([SYSTEMCTL, *args]).returncode == 0


def _need_root():
    if SYSTEMCTL and os.geteuid() != 0:
        _say("run this with sudo")
        return True
    return False


def cmd_list(_):
    have = people.load()
    owner = _owner_settings()
    print("%-24s %s" % (owner.get("steward") or "(the owner)", "owner"))
    for p in have:
        state = "signs in with a passkey" if people.has_key(p["id"]) else "has not signed in yet"
        print("%-24s %s (%s, port %d)" % (p["name"], state, p["id"], p["port"]))
    return 0


def cmd_add(a):
    if _need_root():
        return 1
    owner = _owner_settings()
    if not owner.get("name"):
        _say("this unit has not had its first start yet")
        return 1
    have = people.load()
    err = people.name_error(a.name, have, owner.get("steward"), owner.get("name"))
    if err:
        _say({"in_use": "that name is already somebody's here",
              "reserved": "that name is kept for something else",
              "full": "this unit holds %d people besides the owner" % people.MAX_PEOPLE,
              "too_long": "a name is at most %d characters" % people.NAME_MAX,
              "characters": "a name is letters, digits, spaces, hyphens and apostrophes",
              }.get(err, "that name cannot be used (%s)" % err))
        return 1
    person = people.add(have, a.name)
    root = people.root_dir(person["id"])
    if os.path.lexists(root):
        _say("%s already exists: not touching it" % root)
        return 1
    os.makedirs(os.path.join(root, ".aetherseed"), mode=0o750)
    os.chmod(root, 0o750)
    # the companion is the unit's; who she speaks with here is this person
    _, err = companion.save(os.path.join(root, ".aetherseed", "companion.json"),
                            owner["name"], owner.get("language") or "en", person["name"])
    if err:
        shutil.rmtree(root, ignore_errors=True)
        _say("could not write their settings (%s)" % err)
        return 1
    _chown(root)
    os.makedirs(people.KEYS_DIR, mode=0o700, exist_ok=True)
    os.chmod(people.KEYS_DIR, 0o700)
    _chown(people.KEYS_DIR)
    os.makedirs(ENV_DIR, mode=0o755, exist_ok=True)
    with open(os.path.join(ENV_DIR, person["id"] + ".env"), "w") as f:
        f.write("AETHERSEED_PROXY_PORT=%d\n" % person["port"])
    people.save(have + [person])
    if not _systemctl("enable", "--now", "aetherseed-proxy@%s.service" % person["id"]):
        _say("their proxy did not start: journalctl -u aetherseed-proxy@%s" % person["id"])
        return 1
    _say("%s added. Their first sign-in at the console chooses their passkey." % person["name"])
    return 0


def _find(name):
    have = people.load()
    return have, people.find(have, name)


def cmd_reset(a):
    if _need_root():
        return 1
    _, person = _find(a.name)
    if person is None:
        _say("nobody of that name here")
        return 1
    people.reset(person["id"])
    _systemctl("restart", "aetherseed-gui.service")          # ends their signed-in sessions
    _say("%s's passkey is gone. Their next sign-in chooses a new one." % person["name"])
    return 0


def cmd_remove(a):
    if _need_root():
        return 1
    have, person = _find(a.name)
    if person is None:
        _say("nobody of that name here")
        return 1
    _systemctl("disable", "--now", "aetherseed-proxy@%s.service" % person["id"])
    people.save([p for p in have if p["id"] != person["id"]])
    people.reset(person["id"])
    try:
        os.unlink(os.path.join(ENV_DIR, person["id"] + ".env"))
    except FileNotFoundError:
        pass
    root = people.root_dir(person["id"])
    if os.path.isdir(root):
        aside = "%s.removed-%s" % (root, time.strftime("%Y%m%d-%H%M%S"))
        os.rename(root, aside)
        os.chmod(aside, 0o700)
        _say("%s removed. Their root is kept at %s" % (person["name"], aside))
    else:
        _say("%s removed." % person["name"])
    _systemctl("restart", "aetherseed-gui.service")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    for name, fn in (("add", cmd_add), ("reset", cmd_reset), ("remove", cmd_remove)):
        p = sub.add_parser(name)
        p.add_argument("name")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (OSError, json.JSONDecodeError) as e:
        _say("failed: %r" % (e,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
