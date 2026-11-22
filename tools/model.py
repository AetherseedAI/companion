#!/usr/bin/env python3
"""The model this unit serves (logic/model_switch.py, logic/served.py).

    /opt/aetherseed/tools/model.py list
    sudo /opt/aetherseed/tools/model.py set qwen3:4b

`set` writes /etc/aetherseed/model.env and restarts what serves the model:
every person's proxy and the keep-alive. Talks pause for about a minute while
the new model loads. If the proxy does not come up with the new model, the old
one is put back. Nobody's memory is read or changed.

`--request` is the root side of the console's switch: it reads the model's
name from the console's runtime directory, checks it as `set` does, and leaves
the outcome beside it for the console to show.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic import model_switch as ms          # noqa: E402
from logic import served                      # noqa: E402

REQUEST = os.environ.get("AETHERSEED_MODEL_REQUEST", "/run/aetherseed-gui/model-request")
RESULT = os.environ.get("AETHERSEED_MODEL_RESULT", "/run/aetherseed-gui/model-result")
PEOPLE_ENV = "/etc/aetherseed/people"
STATUS = "http://127.0.0.1:8001/aetherseed/status"


def units():
    out = ["aetherseed-proxy"]
    try:
        out += ["aetherseed-proxy@%s" % f[:-4] for f in sorted(os.listdir(PEOPLE_ENV)) if f.endswith(".env")]
    except OSError:
        pass
    return out


def _run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def _serving(name, wait=120):
    """True once the owner's proxy answers and says it serves `name`."""
    end = time.time() + wait
    while time.time() < end:
        try:
            with urllib.request.urlopen(STATUS, timeout=5) as r:
                if json.load(r).get("model") == name:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def switch(name, say=print):
    """(ok, sentence). Root only."""
    reason = ms.why_not(name)
    if reason:
        return False, "Not switched: %s." % reason
    old = served.configured_model(environ={})
    if old == name:
        ms.write_choices()
        return True, "This unit already serves %s." % name
    us = units()
    say("stopping the proxies and the keep-alive")
    _run("systemctl", "stop", "aetherseed-keepalive", *us)
    ms.write_setting(name)
    say("starting them with %s (the model loads now; about a minute)" % name)
    _run("systemctl", "restart", "hailo-ollama")
    _run("systemctl", "start", *us)
    if not _serving(name):
        say("the proxy did not come up with %s: putting %s back" % (name, old))
        _run("systemctl", "stop", *us)
        ms.write_setting(old)
        _run("systemctl", "restart", "hailo-ollama")
        _run("systemctl", "start", *us)
        _run("systemctl", "start", "aetherseed-keepalive")
        ms.write_choices()
        return False, "Not switched: the proxy did not start with %s. %s is serving again." % (name, old)
    _run("systemctl", "start", "--no-block", "aetherseed-warmup")
    _run("systemctl", "start", "aetherseed-keepalive")
    ms.write_choices()
    return True, "This unit now serves %s (it was %s)." % (name, old)


def from_request():
    """The console asked. The request holds a name and nothing else."""
    try:
        # never through a link: the folder is the console's, the reader root
        fd = os.open(REQUEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, encoding="utf-8") as f:
            name = f.read(64).strip()
    except OSError:
        try:
            os.unlink(REQUEST)
        except OSError:
            pass
        return 0
    try:
        os.unlink(REQUEST)
    except OSError:
        pass
    ok, sentence = switch(name, say=lambda s: print("[model] " + s, flush=True))
    print("[model] " + sentence, flush=True)
    try:
        # Made in root's own folder (the console's folder's parent, /run) and
        # renamed in: a rename replaces a link the console might have left
        # there, where opening "<result>.tmp" in its folder would follow it.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.dirname(RESULT)),
                                   prefix=".aetherseed-model-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"ok": ok, "asked": name if ms.NAME.match(name or "") else None,
                       "message": sentence, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, RESULT)
    except OSError as e:
        print("[model] the outcome could not be left for the console: %r" % (e,), flush=True)
    return 0 if ok else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["list"]:
        now = served.configured_model(environ={})
        for c in ms.choices():
            mark = "serving now" if c["name"] == now else ("ready" if c["ready"] else "no: " + c["why_not"])
            print("%-16s %s" % (c["name"], mark))
        return 0
    if argv == ["--request"]:
        return from_request()
    if len(argv) == 2 and argv[0] == "set":
        if os.geteuid() != 0:
            print("model: run this with sudo", file=sys.stderr)
            return 2
        ok, sentence = switch(argv[1], say=lambda s: print("model: " + s, flush=True))
        print("model: " + sentence)
        return 0 if ok else 1
    if argv == ["choices"]:                    # install.sh: write what the console may offer
        ms.write_choices()
        return 0
    print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
