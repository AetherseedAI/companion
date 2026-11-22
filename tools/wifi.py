#!/usr/bin/env python3
"""Put the unit on a home Wi-Fi, from its console (16 Nov 2026: "The unit should
be able to connect to the wifi regardless. it should broadcast its name
secretly, and anyone who knows it can then connect it to a wifi").

Run as root by aetherseed-wifi.service when the console leaves a request.

    the request (/run/aetherseed-gui/wifi-request, mode 600): one JSON object
      {"action": "scan"}
      {"action": "join", "ssid": "...", "password": "..."}
      {"action": "forget"}
    the result  (/run/aetherseed-gui/wifi-result): one JSON object

THE WAY IN. A phone that knows the unit's hidden network (its name and its
passkey) joins it and opens the console; the console passes the home network
on here. Nothing else about the unit's Wi-Fi changes: tools/hotspot.sh keeps
deciding which network the radio serves (a cable first, then the home Wi-Fi,
then the unit's own hidden network, so a unit is never left unreachable).

THE PASSWORD of the home network goes into one NetworkManager profile,
`aetherseed-home`, written as a key file (root, mode 600) - never onto a
command line, where any process could read it, and never into a log, the
journal or the result.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

REQUEST = os.environ.get("AETHERSEED_WIFI_REQUEST", "/run/aetherseed-gui/wifi-request")
RESULT = os.environ.get("AETHERSEED_WIFI_RESULT", "/run/aetherseed-gui/wifi-result")
NM_DIR = os.environ.get("AETHERSEED_NM_DIR", "/etc/NetworkManager/system-connections")
NMCLI = os.environ.get("AETHERSEED_NMCLI", "nmcli")
SYSTEMCTL = os.environ.get("AETHERSEED_SYSTEMCTL", "systemctl")
HOTSPOT = os.environ.get("AETHERSEED_HOTSPOT_TOOL",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotspot.sh"))
NAME_FILE = os.environ.get("AETHERSEED_WIFI_NAME", "/etc/aetherseed/wifi-home")   # the name only, for the console
RULE_LOCK = os.environ.get("AETHERSEED_HOTSPOT_LOCK", "/run/aetherseed-hotspot.lock")
SCAN_WAKE = float(os.environ.get("AETHERSEED_WIFI_SCAN_WAKE", "4"))
SCAN_WAIT = float(os.environ.get("AETHERSEED_WIFI_SCAN_WAIT", "3"))
SWITCH_DELAY = float(os.environ.get("AETHERSEED_WIFI_SWITCH_DELAY", "3"))
PROFILE = "aetherseed-home"
OWN = "aetherseed-hotspot"
IFACE = "wlan0"


def finish(obj, then_switch=False):
    """Write the result where the console reads it, then (for a join or a
    forget) let the radio follow the rule. Made in /run - root's own folder,
    the console folder's parent - and renamed in, so a link left in the
    console's folder is replaced, never followed."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.dirname(RESULT)), prefix=".aetherseed-wifi-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, RESULT)
    if then_switch:
        # The console has the answer before the radio moves: a phone on the
        # unit's own network loses it the moment the radio joins the home one.
        time.sleep(SWITCH_DELAY)
        subprocess.run(["bash", HOTSPOT, "sync"], capture_output=True)
    sys.exit(0)


def valid_ssid(s):
    # 1-32 bytes, printable, no control characters (a home network's name may
    # hold spaces and quotes: it is never put on a shell line).
    return isinstance(s, str) and 1 <= len(s.encode("utf-8")) <= 32 and s.isprintable() and s == s.strip("\n\r")


def valid_password(p):
    # WPA2-Personal: 8-63 printable ASCII, or 64 hex digits. Empty = an open network.
    if p == "":
        return True
    return isinstance(p, str) and (bool(re.fullmatch(r"[ -~]{8,63}", p)) or bool(re.fullmatch(r"[0-9a-fA-F]{64}", p)))


def keyfile_escape(v):
    """A string value as GLib's key files read it back: a backslash doubled,
    a space at either end written as \\s."""
    v = v.replace("\\", "\\\\")
    if v.startswith(" "):
        v = "\\s" + v[1:]
    if v.endswith(" ") and len(v) > 1:
        v = v[:-1] + "\\s"
    return v


def keyfile_text(ssid, password):
    """A NetworkManager key file. The SSID goes in as bytes (the `ssid=` key
    takes a list of byte values when written that way), so no character in a
    name can break the file. NetworkManager never brings the profile up by
    itself (autoconnect=false): tools/hotspot.sh does, by the rule."""
    ssid_bytes = ";".join(str(b) for b in ssid.encode("utf-8")) + ";"
    lines = ["[connection]", "id=%s" % PROFILE, "type=wifi", "interface-name=%s" % IFACE,
             "autoconnect=false", "", "[wifi]", "mode=infrastructure", "ssid=%s" % ssid_bytes,
             # a hidden home network is found too; a visible one is not harmed by it
             "hidden=true", ""]
    if password:
        if "\n" in password or "\r" in password:
            raise ValueError("password")
        lines += ["[wifi-security]", "key-mgmt=wpa-psk", "psk=%s" % keyfile_escape(password), ""]
    lines += ["[ipv4]", "method=auto", "", "[ipv6]", "method=auto", "addr-gen-mode=stable-privacy", ""]
    return "\n".join(lines)


def write_name(ssid):
    """The network's name (never its password) where the console can show it."""
    d = os.path.dirname(NAME_FILE)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".aetherseed-wifi-home-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(ssid + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, NAME_FILE)


def hold_rule_lock():
    """tools/hotspot.sh's lock (flock on the same file), or None where it
    cannot be opened (a test)."""
    import fcntl
    try:
        f = open(RULE_LOCK, "a")
    except OSError:
        return None
    fcntl.flock(f, fcntl.LOCK_EX)
    return f


def nm(*args):
    return subprocess.run([NMCLI] + list(args), capture_output=True, text=True)


def saved_ssid():
    path = os.path.join(NM_DIR, PROFILE + ".nmconnection")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("ssid="):
                    v = line.strip()[5:]
                    if re.fullmatch(r"(\d{1,3};)+", v):
                        return bytes(int(x) for x in v.strip(";").split(";")).decode("utf-8", "replace")
                    return v
    except OSError:
        pass
    return None


def scan():
    """The networks the radio can see. While it serves the unit's own network
    it may see none (an access point scans poorly on many chips): the console
    then lets the name be typed."""
    # With a cable in, the rule keeps the radio off: it is switched on for the
    # scan alone and off again after (seen on a unit, 16 Nov: a scan with the
    # cable in found nothing).
    # The rule's lock is held meanwhile, so its clock does not switch the
    # radio off in the middle of the scan.
    lock = hold_rule_lock()
    was_off = nm("radio", "wifi").stdout.strip() != "enabled"
    if was_off:
        nm("radio", "wifi", "on")
        time.sleep(SCAN_WAKE)
    nm("device", "wifi", "rescan", "ifname", IFACE)
    time.sleep(SCAN_WAIT)
    r = nm("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", IFACE)
    if was_off:
        nm("radio", "wifi", "off")
    if lock is not None:
        lock.close()
    seen = {}
    for line in r.stdout.splitlines():
        # nmcli -t escapes ':' in values as '\:'
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3:
            continue
        ssid = parts[0].replace("\\:", ":")
        if not ssid or not valid_ssid(ssid):
            continue
        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0
        secure = parts[2] not in ("", "--")
        if ssid not in seen or seen[ssid]["signal"] < signal:
            seen[ssid] = {"ssid": ssid, "signal": signal, "secure": secure}
    nets = sorted(seen.values(), key=lambda n: -n["signal"])[:20]
    finish({"ok": True, "action": "scan", "networks": nets})


def join(ssid, password):
    if not valid_ssid(ssid):
        finish({"ok": False, "code": "bad_ssid", "error": "Not a network name."})
    if not valid_password(password):
        finish({"ok": False, "code": "bad_password",
                "error": "A Wi-Fi password has 8 to 63 characters."})
    text = keyfile_text(ssid, password)
    del password
    os.makedirs(NM_DIR, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=NM_DIR, prefix=".aetherseed-home-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, os.path.join(NM_DIR, PROFILE + ".nmconnection"))
    del text
    nm("connection", "reload")
    write_name(ssid)
    # A unit set up without a network of its own has no rule running yet: the
    # rule (and the Wi-Fi client under it) is switched on with the first home
    # network, so the fall-back and the retries work there too.
    for unit in ("wpa_supplicant", "aetherseed-hotspot"):
        subprocess.run([SYSTEMCTL, "enable", "--now", unit], capture_output=True)
    print("[wifi] a home network was saved; the radio follows the rule", flush=True)
    finish({"ok": True, "action": "join", "ssid": ssid}, then_switch=True)


def forget():
    nm("connection", "down", PROFILE)
    nm("connection", "delete", PROFILE)
    try:
        os.unlink(os.path.join(NM_DIR, PROFILE + ".nmconnection"))
    except OSError:
        pass
    nm("connection", "reload")
    try:
        os.unlink(NAME_FILE)
    except OSError:
        pass
    print("[wifi] the home network was forgotten", flush=True)
    finish({"ok": True, "action": "forget"}, then_switch=True)


def main():
    try:
        fd = os.open(REQUEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)    # never through a link
        with os.fdopen(fd, encoding="utf-8") as f:
            raw = f.read(4096)
    except OSError:
        finish({"ok": False, "code": "no_request", "error": "Nothing was asked."})
    finally:
        try:
            os.unlink(REQUEST)
        except OSError:
            pass
    try:
        req = json.loads(raw)
    except ValueError:
        req = None
    if not isinstance(req, dict):
        finish({"ok": False, "code": "bad_request", "error": "Not a request."})
    action = req.get("action")
    if action == "scan":
        scan()
    if action == "join":
        join(req.get("ssid"), req.get("password", ""))
    if action == "forget":
        forget()
    finish({"ok": False, "code": "bad_request", "error": "Not a request."})


if __name__ == "__main__":
    main()
