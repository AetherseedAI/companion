"""Claude, straight from the unit: the Anthropic Messages API (21 Nov 2026).

WHY. The operator, 21 Nov 2026: "lets go for the anthropic direct now, and
again I want it that on all units." The Windows runtime ARC 0.7 is
Windows-only and listens on loopback, so a unit talks to Anthropic itself.

WHOSE ACCESS. Aetherseed is not a subscription. The owner brings their own,
legally obtained Anthropic API key and pays Anthropic for what is used. The
key is stored on the unit, in the companion's state folder, readable only by
the companion's own user (0600). It is never shown again after it is set:
the console sees only whether one is set and its last four characters.

WHAT GOES, WHAT STAYS. Claude answers as the companion, from the same prompt
the local model would get: the charter, the journal lines, the conversation
in progress. Except the vault: a turn the person marked as vaulted is
answered by the local model, kept in the journal as private, never put in
the conversation in progress, and never sent. When private entries were
left out of a prompt, Claude is told so in one line, and not what they hold.
The protection is against someone between the unit and Anthropic reading
them, not against Anthropic.

WHEN CLAUDE IS NOT THERE. Any failure - no network, a refused key, a
timeout - and the turn is answered by the local model, and the badge says
so. AetherSeed stays useful when the cloud is down.

Only api.anthropic.com is ever contacted, and only over HTTPS with the
system's certificate store. The firewall (services/nftables.conf) lets the
companion's own user, and nobody else on the unit, ask a name server and
open HTTPS.
"""
import json
import os
import ssl
import tempfile
import threading
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = os.environ.get("AETHERSEED_CLAUDE_MODEL", "claude-sonnet-5-5")
MODEL_CHOICES = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5")
MAX_TOKENS = 1024
MAX_TOKENS_WRITING = 4096
TIMEOUT_S = 60
KEY_FILE = "anthropic.key"
CONFIG_FILE = "cloud.json"

# Said to Claude, under the unit's own prompt.
PERSONA_NOTE = ("You are answering through this unit as {name}, in {name}'s voice and "
                "manner, for the people {name} lives with. The journal lines are what "
                "they told {name}. Say plainly when you do not know something.")
WITHHELD_NOTE = ("{n} thing(s) said to {name} are kept in a private vault at home and are "
                 "not shown here. Do not guess at them or ask about them.")


# "Are you connected to the cloud?" while Claude is on: the build's line says
# nothing leaves the device, which is then not true. Said instead, by the unit
# (logic/knowledge.py self.local), and put in Claude's prompt in its place.
LOCAL_LINE = ("Nothing said to me leaves this device. There is no cloud behind me, "
              "no account, and no subscription.")
CLAUDE_ON_LINE = ("My owner has switched Claude on: what we talk about goes to Anthropic "
                  "so that Claude can answer as me, except what you mark Vault, which "
                  "stays here. My memory, my library and my model are on this device, "
                  "and I answer here myself when Claude cannot be reached.")


class CloudError(Exception):
    """Claude did not answer; the local model will."""


class Cloud:
    def __init__(self, folder, opener=None):
        self.folder = folder
        self._lock = threading.Lock()
        # tests hand in their own opener; the unit uses urllib's
        self._open = opener or self._urlopen

    # ---- settings ----------------------------------------------------
    def _path(self, name):
        return os.path.join(self.folder, name)

    def _config(self):
        try:
            with open(self._path(CONFIG_FILE)) as f:
                c = json.load(f)
            return c if isinstance(c, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, name, text):
        os.makedirs(self.folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.folder, prefix="." + name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path(name))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _key(self):
        try:
            with open(self._path(KEY_FILE)) as f:
                return f.read().strip()
        except OSError:
            return ""

    def status(self):
        c, k = self._config(), self._key()
        return {"on": bool(c.get("on")) and bool(k), "switched_on": bool(c.get("on")),
                "key": bool(k), "key_end": k[-4:] if k else "",
                "model": c.get("model") or DEFAULT_MODEL, "models": list(MODEL_CHOICES)}

    def ready(self):
        return self.status()["on"]

    def set_key(self, key):
        key = (key or "").strip()
        if not key.startswith("sk-ant-") or len(key) < 24 or len(key) > 300 \
                or any(c.isspace() for c in key):
            raise ValueError("bad_key")
        with self._lock:
            self._write(KEY_FILE, key + "\n")

    def forget_key(self):
        with self._lock:
            try:
                os.unlink(self._path(KEY_FILE))
            except FileNotFoundError:
                pass
            c = self._config()
            c["on"] = False
            self._write(CONFIG_FILE, json.dumps(c))

    def switch(self, on=None, model=None):
        with self._lock:
            c = self._config()
            if on is not None:
                c["on"] = bool(on)
            if model is not None:
                if model not in MODEL_CHOICES:
                    raise ValueError("bad_model")
                c["model"] = model
            self._write(CONFIG_FILE, json.dumps(c))

    # ---- one answer --------------------------------------------------
    @staticmethod
    def as_request(messages):
        """The local model's messages, as the Messages API takes them: the
        system lines together, then turns that alternate and begin with the
        person."""
        system = "\n\n".join(m["content"] for m in messages
                             if m.get("role") == "system" and m.get("content"))
        turns = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant") or not (m.get("content") or "").strip():
                continue
            if turns and turns[-1]["role"] == role:
                turns[-1]["content"] += "\n\n" + m["content"]
            else:
                turns.append({"role": role, "content": m["content"]})
        while turns and turns[0]["role"] != "user":
            turns.pop(0)
        if not turns:
            raise CloudError("nothing to ask")
        return system, turns

    def _urlopen(self, req, timeout):
        ctx = ssl.create_default_context()
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)

    def stream(self, messages, on_text, writing=False):
        """Ask Claude; on_text(piece) for each piece as it comes. Returns the
        whole text. Raises CloudError on anything that is not an answer."""
        key = self._key()
        st = self.status()
        if not st["on"]:
            raise CloudError("not switched on")
        system, turns = self.as_request(messages)
        body = {"model": st["model"], "max_tokens": MAX_TOKENS_WRITING if writing else MAX_TOKENS,
                "stream": True, "messages": turns}
        if system:
            body["system"] = system
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST",
                                     headers={"x-api-key": key,
                                              "anthropic-version": API_VERSION,
                                              "content-type": "application/json",
                                              "accept": "text/event-stream"})
        text = []
        try:
            resp = self._open(req, TIMEOUT_S)
        except urllib.error.HTTPError as e:
            raise CloudError("HTTP %s" % e.code)
        except Exception as e:
            raise CloudError("unreachable: %s" % type(e).__name__)
        try:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                    piece = ev["delta"].get("text", "")
                    if piece:
                        text.append(piece)
                        on_text(piece)
                elif kind == "error":
                    raise CloudError("error: %s" % (ev.get("error") or {}).get("type", "?"))
                elif kind == "message_stop":
                    break
        except CloudError:
            if text:
                return "".join(text)        # what came is shown; the rest is lost
            raise
        except Exception as e:
            if text:
                return "".join(text)
            raise CloudError("stream broke: %s" % type(e).__name__)
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not text:
            raise CloudError("empty answer")
        return "".join(text)
