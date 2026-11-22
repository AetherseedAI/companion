"""The steward file: who the steward is and what they prefer, in their words.

    ~/aetherseed-workspace/steward.md

A plain Markdown file at the top of the workspace, so the steward can read and
edit it in the console's editor. The companion adds to it when the steward
tells it to, and only then:

    "Remember that I prefer short answers."       -> Preferences
    "Note that I like gardening."                 -> Preferences
    "Call me Sam."                               -> Preferences
    "Remember that my daughter is called Mia."    -> About me
    "Remember that I work as a nurse."            -> About me
    "Remove gardening from my steward file."      -> the item that holds it goes
    "What do you know about me?"                  -> the file, read out

What is kept is what the steward said, word for word, never the model's
summary of it: a line here goes into every prompt of the steward's own turns,
so a paraphrase would be the model's words returning as the steward's. A guest
never adds to it, never hears it, and never has it in a prompt. The steward's
name is not here; it is the unit's setting (logic/companion.py), part of the
sign-in. Every change is one line in workspace.log (the path and the size,
not the text).
"""
import os
import re
from pathlib import Path

FILE = "steward.md"
PREFS = "Preferences"
ABOUT = "About me"
SECTIONS = (PREFS, ABOUT)
MAX_ITEM = 200
MAX_ITEMS = 30
PROMPT_CHARS = 420          # of the system prompt, at most

TEMPLATE = """# Steward

What your companion keeps about you, in your own words. It adds a line when you
tell it to ("Remember that I prefer short answers"); you can edit this file
here. One item per line, starting with "- ".

## Preferences

## About me
"""


class StewardFileError(ValueError):
    pass


def path(ws):
    return Path(ws) / FILE


def ensure(ws):
    p = path(ws)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "x", encoding="utf-8") as f:
            f.write(TEMPLATE)
    return p


def items(ws):
    """{section: [item, ...]} as the file stands now."""
    out = {s: [] for s in SECTIONS}
    try:
        lines = path(ws).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    cur = None
    for line in lines:
        h = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if h:
            cur = next((s for s in SECTIONS if s.lower() == h.group(1).lower()), None)
            continue
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if m and cur:
            out[cur].append(m.group(1))
    return out


def clean_item(text):
    t = " ".join(str(text or "").split()).strip(" .")
    if not t:
        raise StewardFileError("nothing to keep")
    if len(t) > MAX_ITEM:
        raise StewardFileError("that is longer than %d characters" % MAX_ITEM)
    if re.search(r"[\[\]|<>{}]", t):
        raise StewardFileError("brackets, pipes and angle brackets are not kept")
    return t[0].upper() + t[1:]


def _write(ws, sections):
    p = ensure(ws)
    lines = p.read_text(encoding="utf-8").splitlines()
    head = []
    for line in lines:
        if re.match(r"^\s*##\s+", line):
            break
        head.append(line)
    body = []
    for s in SECTIONS:
        body += ["## " + s, ""] + ["- " + i for i in sections[s]] + [""]
    text = "\n".join(head).rstrip() + "\n\n" + "\n".join(body).rstrip() + "\n"
    tmp = p.with_suffix(".md.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return len(text.encode("utf-8"))


def add(ws, section, text):
    """Add an item; returns (item, size). An item already there is not added twice."""
    if section not in SECTIONS:
        raise StewardFileError("no such section")
    item = clean_item(text)
    s = items(ws)
    if sum(len(v) for v in s.values()) >= MAX_ITEMS:
        raise StewardFileError("the file holds %d items already; remove one first" % MAX_ITEMS)
    if any(i.casefold() == item.casefold() for i in s[section]):
        return item, None
    s[section].append(item)
    return item, _write(ws, s)


def remove(ws, words):
    """Remove the one item that holds `words`. Returns (removed, size), or
    raises when none or more than one holds them."""
    w = " ".join(str(words or "").casefold().split())
    if not w:
        raise StewardFileError("which item?")
    s = items(ws)
    hits = [(sec, i) for sec in SECTIONS for i in s[sec] if w in i.casefold()]
    if not hits:
        raise StewardFileError("nothing in your steward file holds \"%s\"" % words)
    if len(hits) > 1:
        raise StewardFileError("more than one item holds \"%s\": %s" % (
            words, "; ".join(i for _, i in hits)))
    sec, item = hits[0]
    s[sec].remove(item)
    return item, _write(ws, s)


def said_text(ws):
    """The file, as the companion says it."""
    s = items(ws)
    if not any(s.values()):
        return ("Your steward file is empty. Tell me \"Remember that I prefer ...\" "
                "and I will keep it there, in your words.")
    parts = []
    if s[PREFS]:
        parts.append("Your preferences: " + "; ".join(s[PREFS]) + ".")
    if s[ABOUT]:
        parts.append("About you: " + "; ".join(s[ABOUT]) + ".")
    return " ".join(parts)


def prompt_block(ws):
    """The lines for the system prompt of a steward's turn, or ""."""
    s = items(ws)
    lines = ["- " + i for sec in SECTIONS for i in s[sec]]
    if not lines:
        return ""
    out = ["What your steward told you about themselves, in their words:"]
    used = len(out[0])
    for line in lines:
        if used + len(line) + 1 > PROMPT_CHARS:
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out) if len(out) > 1 else ""


# ---- what the steward said -------------------------------------------------
_PREF = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|keep\s+in\s+mind)(?:\s+that)?\s+"
    r"(i\s+(?:prefer|like|love|enjoy|dislike|hate|want|don['’]?t\s+like|do\s+not\s+like)\b.+?)"
    r"\s*[.!]*\s*$", re.I)
_PREF2 = re.compile(r"^\s*my\s+preference\s+is\s+(?:that\s+)?(.+?)\s*[.!]*\s*$", re.I)
_CALL = re.compile(r"^\s*(?:please\s+)?call\s+me\s+([A-Za-zÀ-ÿ][\w\-']{0,19}(?:\s+[A-Za-zÀ-ÿ][\w\-']{0,19})?)\s*[.!]*\s*$", re.I)
_NOT_A_NAME = set("later back tomorrow tonight today when now soon again sometime if at in on please maybe".split())
_ABOUT = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|keep\s+in\s+mind)(?:\s+that)?\s+"
    r"((?:my\s+|i\s+(?:am|work|live|have|was|grew)\b|i['’]m\b).+?)\s*[.!]*\s*$", re.I)
_REMOVE = re.compile(
    r"^\s*(?:please\s+)?(?:remove|delete|take)\s+(.+?)\s+(?:from|off|out\s+of)\s+"
    r"(?:my\s+|the\s+)?steward(?:['’]s)?\s+file\s*[.!]*\s*$", re.I)
_SHOW = re.compile(
    r"^\s*(?:what\s+do\s+you\s+know\s+about\s+me|what\s+are\s+my\s+preferences|"
    r"(?:show|read)\s+(?:me\s+)?my\s+steward\s+file|what(?:'s|’s|\s+is)\s+in\s+my\s+steward\s+file)"
    r"\s*[?.!]*\s*$", re.I)


def parse(msg):
    """("add", section, text) | ("remove", words) | ("show",) | None."""
    t = (msg or "").strip()
    if not t or len(t) > 260 or "\n" in t:
        return None
    if _SHOW.match(t):
        return ("show",)
    m = _REMOVE.match(t)
    if m:
        return ("remove", m.group(1).strip(" '\"“”‘’"))
    m = _PREF.match(t)
    if m:
        return ("add", PREFS, m.group(1))
    m = _PREF2.match(t)
    if m:
        return ("add", PREFS, "My preference is " + m.group(1))
    m = _CALL.match(t)
    if m and not (set(m.group(1).lower().split()) & _NOT_A_NAME):
        return ("add", PREFS, "Call me " + m.group(1).strip())
    m = _ABOUT.match(t)
    if m:
        return ("add", ABOUT, m.group(1))
    return None
