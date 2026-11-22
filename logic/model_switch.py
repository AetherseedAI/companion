"""Which models this unit can be switched to, and the switch itself.

The served model is the unit's own setting (logic/served.py):
/etc/aetherseed/model.env. It is changed by root only - by tools/model.py at a
shell, or, asked for by the owner at the console, by the root-side unit
services/aetherseed-model.service, which runs the same tool. The console
itself changes nothing: it leaves the model's NAME in its runtime directory,
as it does for a power-off, and the root side checks the name again.

A model can be chosen when all three hold:
  - this build has a profile for it with a MEASURED prompt ceiling
    (logic/token_budget.MODELS) - never served on a guess;
  - its file is in hailo-ollama's store;
  - its tokenizer is on the unit.
One Hailo device holds one model at a time, so the setting is the unit's, not
a person's: every person's proxy serves the same model.
"""
import json
import os
import re

MODEL_FILE = "/etc/aetherseed/model.env"
CHOICES_FILE = "/etc/aetherseed/models.json"      # what the console may offer; written by root
BLOB_DIR = "/usr/share/hailo-ollama/models/blob"
STATE = "/var/lib/aetherseed"
NAME = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,30}:[a-z0-9.\-]{1,12}$")

# The start of each model's file name in hailo-ollama's store.
FILES = {
    "qwen3:1.7b": "Qwen3-1.7B-",
    "qwen3:4b": "Qwen3-4B-",
    "qwen2.5:1.5b": "Qwen2.5-1.5B-",
    "llama3.2:1b": "Llama3.2-1B-",
}


def profiles():
    from logic.token_budget import MODELS
    return MODELS


def in_store(name, blob_dir=None):
    start = (profiles().get(name) or {}).get("store_file") or FILES.get(name)
    if not start:
        return False
    try:
        names = os.listdir(blob_dir or BLOB_DIR)
    except OSError:
        return False
    return any(n.startswith(start) and n.endswith(".hef") for n in names)


def has_tokenizer(name, state=None):
    tok = (profiles().get(name) or {}).get("tokenizer")
    return bool(tok) and os.path.exists(os.path.join(state or STATE, tok))


def why_not(name, blob_dir=None, state=None):
    """None when the unit can serve it, else the reason in a sentence."""
    if not isinstance(name, str) or not NAME.match(name):
        return "that is not a model's name"
    profile = profiles().get(name)
    if profile is None:
        return "this build has no profile for %s" % name
    if profile.get("ceiling") is None:
        return "the prompt ceiling of %s has not been measured" % name
    if not in_store(name, blob_dir):
        return "the file of %s is not in the model store" % name
    if not has_tokenizer(name, state):
        return "the tokenizer of %s is not on this unit" % name
    return None


def choices(blob_dir=None, state=None):
    """Every model of this build, with whether the unit can serve it now."""
    out = []
    for name in sorted(profiles()):
        reason = why_not(name, blob_dir, state)
        out.append({"name": name, "ready": reason is None, "why_not": reason})
    return out


def write_choices(path=None, blob_dir=None, state=None):
    path = path or CHOICES_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"models": choices(blob_dir, state)}, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def write_setting(name, path=None):
    """The one line the services read. Atomic: never a half-written file."""
    path = path or MODEL_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("AETHERSEED_MODEL=%s\n" % name)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
