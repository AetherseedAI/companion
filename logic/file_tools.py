"""Her file tools: save, append, make a folder, move, delete to the trash -
asked for in words, done by the unit, said by the unit.

WHY (plan-workspace-tools, 13 Nov 2026): asked on a PC for a story saved
as a .docx, the 4B said it could make .docx, said "Done!", gave a path and
said it had moved the file. No tool matched any of the ten messages, and the
unit had no tool that writes a named file. test_workspace_replay.py replays
them.

THE RULE: the model may write the words; the unit writes the file and says
so - "Saved: <path> (<n> bytes)". A file action is never confirmed in the
model's words. A reply that claims one where no file tool ran is followed by
the unit's own line saying nothing was saved, and is kept out of memory
(claims_a_file_action, proxy.py).

WHAT IS WRITTEN: text only, Markdown (.md) or plain text (.txt). A name asked
with another format (.docx, .pdf) is saved as .md under the same name, and the
unit says why. Paths go through logic/workspace (inside the workspace, no "..",
no link out, 200 KB, five folders deep) and through may_reach: a folder of a
trust level above hers is closed, as for every other tool of hers. A new file
never replaces one that is there. A delete moves the file to .trash/, never
removes it; the four level folders cannot be moved or deleted.

THE WORDS: the saves are read from the message by parse() below, before the
intent patterns (detect_intent). "save it as story.md", "put it in the
builder folder", "write a story about ... and save it as story.md" (the model
writes, then the unit saves what it wrote), "append it to story.md", "make a
folder called stories", "move story.md to stories", "delete the file
story.md". Every one needs a verb of saving and a thing to save or a file, so
"save money" or "I saved the day" is no request.
"""
import os
import re
from datetime import datetime
from pathlib import Path

from logic import workspace as W

TEXT_EXT = (".md", ".txt")
TRASH = ".trash"
NAME_MAX = 80

# a quoted name, or a name with an extension, or a path, or one plain word
_QUOTED = r"['\"‘“]([^'\"’”\n]{1,120})['\"’”]"
_FILE = r"([\w][\w.\-/]*\.[A-Za-z]{1,5})\b"
_WORD = r"([\w][\w.\-/]*)"
_OTHER_FORMAT = re.compile(r"\b(?:docx?|pdf|odt|rtf|pptx?|xlsx?|pages|word|excel|powerpoint)\b", re.I)
_FORMAT_WORD = re.compile(
    r"\b(?:in|as|into|to)\s+(?:a|an)?\s*\.?(docx?|pdf|odt|rtf|word|markdown|md|txt|text|plain\s+text)"
    r"\s*(?:file|format|document|doc)?\b", re.I)
# the things one saves: "it", "this", "the story", "your answer"
_THING = (r"(?:it|this|that|these|the\s+(?:file|story|poem|text|answer|reply|list|letter|recipe|"
          r"summary|song|tale|plan|essay|draft|note|words)|your\s+(?:last\s+)?(?:answer|reply|story|poem))")
_SAVE = re.compile(
    r"\b(?:save|store|put|place|write)\s+" + _THING +
    r"(?=\s+(?:as|in|into|to|inside|under|named|called)\b|\s*$|\s*[.!?,])", re.I)
_NAMED = re.compile(
    r"\b(?:name|call|title)\s+(?:it|the\s+file)\s+(?:as\s+)?(?:" + _QUOTED + r"|(.+?))\s*[.!?]*\s*$"
    r"|\b(?:called|named|titled)\s+(?:" + _QUOTED + r"|" + _FILE + r"|(.+?))"
    r"(?=\s+(?:in|into|to|inside)\s+(?:the|my|your)\s+[\w-]+\s+folder\b|\s*[.!?]*\s*$)", re.I)
_AS_FILE = re.compile(
    r"\b(?:as|to|into|in)\s+(?:a\s+|the\s+)?(?:new\s+)?(?:file\s+)?(?:" + _QUOTED + r"|" + _FILE + r")",
    re.I)
_FOLDER = re.compile(r"\b(?:in|into|to|inside|under)\s+(?:the\s+|my\s+|your\s+)?"
                     r"(?!(?:the|my|your|a|an|this|that)\b)([\w-]+)\s+folder\b", re.I)
# the message also asks for something to be written: then the model writes it
# first, and the unit saves what it wrote
_COMPOSE = re.compile(
    r"\b(?:write|writing|compose|draft|make\s+up|tell|create)\b.{0,200}?\b(?:story|stories|poem|song|"
    r"letter|list|recipe|essay|summary|tale|plan|speech|text|lyrics|description)\b", re.I | re.S)
_WRITE_IN_FORMAT = re.compile(
    r"\b(?:write|writing|rewrite)\b.{0,80}?\b(?:in|as)\s+(?:a|an)?\s*\.?(?:md|markdown|txt|text)\s*"
    r"(?:format|file)\b", re.I | re.S)

_APPEND = re.compile(
    r"\b(?:append|add)\s+(?:" + _THING + r")\s+to\s+(?:the\s+|my\s+)?(?:file\s+)?(?:" + _QUOTED + r"|" + _FILE + r")",
    re.I)
_APPEND_TEXT = re.compile(
    r"\b(?:append|add)\s+to\s+(?:the\s+|my\s+)?(?:file\s+)?(?:" + _QUOTED + r"|" + _FILE + r")\s*:\s*(.+)$",
    re.I | re.S)
_WRITE_TEXT = re.compile(
    r"\b(?:write|save)\s+(?:to|in|into)\s+(?:a\s+|the\s+)?(?:new\s+)?file\s+(?:" + _QUOTED + r"|" + _WORD + r")\s*:\s*(.+)$",
    re.I | re.S)
_MKDIR = re.compile(
    r"\b(?:make|create|add|start)\s+(?:a\s+|an\s+)?(?:new\s+)?folder\s+(?:called\s+|named\s+)?(?:" + _QUOTED + r"|" + _WORD + r")",
    re.I)
_MOVE = re.compile(
    r"\b(?:move|rename)\s+(?:the\s+)?(?:file\s+)?(?:" + _QUOTED + r"|" + _FILE + r")\s+(?:to|into|as)\s+"
    r"(?:the\s+)?(?:folder\s+)?(?:" + _QUOTED + r"|" + _WORD + r")(?:\s+folder)?", re.I)
_DELETE = re.compile(
    r"\b(?:delete|remove|trash|bin)\s+(?:the\s+)?(?:file\s+(?:" + _QUOTED + r"|" + _WORD + r")|(?:" + _QUOTED + r"|" + _FILE + r"))",
    re.I)

TOOLS = ("file_save", "file_append", "file_write", "folder_make", "file_move", "file_delete")
DESTRUCTIVE = frozenset({"file_move", "file_delete"})
DESCRIPTION = {
    "file_save": "Save an answer as a file",
    "file_append": "Add to the end of a file",
    "file_write": "Write a new file",
    "folder_make": "Make a folder",
    "file_move": "Move or rename a file",
    "file_delete": "Move a file to the trash",
}


def _first(*groups):
    for g in groups:
        if g and g.strip():
            return g.strip()
    return None


def _intent(name, captures, message):
    return {"intent": name, "description": DESCRIPTION[name], "tier": 2, "soft": False,
            "match": message.strip()[:120], "captures": captures, "original": message}


def parse(message):
    """The file request in `message`, as an intent dict, or None.

    captures:
      file_save   (name or None, folder or None, format word or None, "after"|"last")
      file_append (name, text or None)          None: her last answer
      file_write  (name, text)
      folder_make (name,)
      file_move   (from, to)
      file_delete (name,)
    """
    if not isinstance(message, str) or not message.strip():
        return None
    m = message.strip()
    if re.search(r"\bto-?do\b|\btask\s+list\b", m, re.I):
        return None                                   # the to-do list has its own tools

    a = _APPEND_TEXT.search(m)
    if a:
        return _intent("file_append", (_first(a.group(1), a.group(2)), a.group(3).strip()), message)
    a = _APPEND.search(m)
    if a:
        return _intent("file_append", (_first(a.group(1), a.group(2)), None), message)
    w = _WRITE_TEXT.search(m)
    if w:
        return _intent("file_write", (_first(w.group(1), w.group(2)), w.group(3).strip()), message)
    k = _MKDIR.search(m)
    if k:
        return _intent("folder_make", (_first(k.group(1), k.group(2)),), message)
    mv = _MOVE.search(m)
    if mv:
        return _intent("file_move", (_first(mv.group(1), mv.group(2)),
                                     _first(mv.group(3), mv.group(4))), message)
    d = _DELETE.search(m)
    if d:
        return _intent("file_delete", (_first(*d.groups()),), message)

    saving = _SAVE.search(m)
    in_format = _WRITE_IN_FORMAT.search(m)
    if not saving and not in_format:
        return None
    name = None
    n = _NAMED.search(m)
    if n:
        name = _first(*n.groups())
    if not name:
        f = _AS_FILE.search(m)
        if f:
            name = _first(f.group(1), f.group(2))
    folder = None
    fo = _FOLDER.search(m)
    if fo:
        folder = fo.group(1)
    fmt = None
    fw = _FORMAT_WORD.search(m)
    if fw:
        fmt = fw.group(1).lower()
    if not (name or folder or fmt or in_format):
        return None                    # "keep it short", "put it simply": nothing to save to
    when = "after" if (_COMPOSE.search(m) or in_format) else "last"
    return _intent("file_save", (name, folder, fmt, when), message)


# ---- names -------------------------------------------------------------------

def file_name(raw, fmt=None, text=None):
    """(relative name, note): the name to write, as Markdown or text, and a
    sentence when the name asked for was changed (another format)."""
    note = None
    name = (raw or "").strip()
    if not name and text:
        name = title_of(text)
    if not name:
        name = "saved-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    # the quotes and the characters a name does not carry
    name = re.sub(r"['\"‘’“”*`<>|:?\\]", "", name)
    name = re.sub(r"\s+", " ", name).strip(" ./")
    stem, ext = os.path.splitext(name)
    asked_other = (ext and ext.lower() not in TEXT_EXT and _OTHER_FORMAT.search(ext)) or \
        (fmt and _OTHER_FORMAT.search(fmt))
    if ext.lower() in TEXT_EXT:
        pass
    else:
        if ext and _OTHER_FORMAT.search(ext):
            name = stem
        name = name + (".txt" if fmt in ("txt", "text", "plain text") else ".md")
    if asked_other:
        what = (ext or "." + (fmt or "")).lower().lstrip(".")
        what = {"word": "docx", "doc": "docx", "excel": "xlsx", "powerpoint": "pptx"}.get(what, what)
        note = ("I can't make .%s files; I write text only, so it is saved as Markdown, "
                "which any text editor opens." % what)
    if len(name) > NAME_MAX:
        stem, ext = os.path.splitext(name)
        name = stem[:NAME_MAX - len(ext)].rstrip() + ext
    return name, note


def title_of(text):
    """A name for an answer saved without one: its heading, or its first words."""
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        t = re.sub(r"^#+\s*", "", t)
        t = re.sub(r"[*_`\"“”]", "", t).strip()
        words = t.split()
        if words:
            return " ".join(words[:8])
    return None


# ---- what the unit does --------------------------------------------------------

def _human(n):
    return "{:,}".format(n)


def _err(what, e):
    msg = getattr(e, "message", None) or str(e)
    return "I could not %s: %s. Nothing was written." % (what, msg)


def _closed(rel, level):
    if not W.may_reach(rel, level):
        return W.closed_text(rel, level)
    return None


def save_new(ws, rel, text, level, note=None):
    """A new file with `text`. Never replaces one that is there."""
    closed = _closed(rel, level)
    if closed:
        return closed
    if not (text or "").strip():
        return "There is nothing to save yet: I have no answer of mine in this conversation. Nothing was written."
    try:
        _root, p, rel = W.resolve(ws, rel)
        if p.exists():
            return ("A file called %s is already there, so I did not write over it. "
                    "Say another name, or \"append it to %s\". Nothing was written." % (rel, rel))
        r = W.save(ws, rel, text if text.endswith("\n") else text + "\n")
    except W.WorkspaceError as e:
        return _err("save that", e)
    out = "Saved: %s (%s bytes)." % (r["path"], _human(r["size"]))
    return (note + " " + out) if note else out


def append(ws, rel, text, level):
    closed = _closed(rel, level)
    if closed:
        return closed
    if not (text or "").strip():
        return "There is nothing to add: I have no answer of mine in this conversation. Nothing was written."
    try:
        _root, p, rel = W.resolve(ws, rel)
        before = ""
        if p.is_file():
            before = W.read(ws, rel)["text"]
            if before and not before.endswith("\n"):
                before += "\n"
            before += "\n"
        r = W.save(ws, rel, before + text.rstrip("\n") + "\n")
    except W.WorkspaceError as e:
        return _err("add to that file", e)
    return "Saved: %s (%s bytes; added to the end)." % (r["path"], _human(r["size"]))


def make_folder(ws, rel, level):
    closed = _closed(rel, level)
    if closed:
        return closed
    try:
        r = W.mkdir(ws, rel)
    except W.WorkspaceError as e:
        return _err("make that folder", e)
    return "Made the folder %s/." % r["path"]


def move(ws, src, dst, level):
    for rel in (src, dst):
        closed = _closed(rel, level)
        if closed:
            return closed
    try:
        _r, p, src = W.resolve(ws, src)
        _r, q, dst = W.resolve(ws, dst)
        if not p.is_file():
            return "There is no file %s in my workspace. Nothing was moved." % src
        if q.is_dir():
            dst = (Path(dst) / p.name).as_posix()
        elif not os.path.splitext(dst)[1]:
            # "move story.md to stories": a folder that is not there yet
            if "/" not in dst and not q.exists():
                dst = (Path(dst) / p.name).as_posix()
        closed = _closed(dst, level)
        if closed:
            return closed
        r = W.rename(ws, src, dst)
    except W.WorkspaceError as e:
        return "I could not move that: %s. Nothing was moved." % (getattr(e, "message", e))
    return "Moved: %s -> %s." % (r["from"], r["to"])


def to_trash(ws, rel, level):
    closed = _closed(rel, level)
    if closed:
        return closed
    try:
        _r, p, rel = W.resolve(ws, rel)
        if rel.lower() in W.LADDER:
            return "The four trust-level folders stay. Nothing was deleted."
        if not p.is_file():
            return "There is no file %s in my workspace. Nothing was deleted." % rel
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = "%s/%s-%s" % (TRASH, stamp, p.name)
        root = Path(ws).resolve()
        (root / TRASH).mkdir(exist_ok=True)
        os.rename(p, root / dst)
    except (W.WorkspaceError, OSError) as e:
        return "I could not delete that: %s. Nothing was deleted." % (getattr(e, "message", e))
    return "Moved to the trash: %s (now %s; it can be moved back)." % (rel, dst)


_UNIT_LINE = re.compile(r"^\s*(?:Saved: |Moved: |Made the folder |\(From the unit: |I can't make \.\w+ files;).*$", re.M)


def without_unit_lines(text):
    """An answer as the model wrote it: the unit's own lines after it taken out."""
    return _UNIT_LINE.sub("", text or "").strip()


def asks_to_compose(message):
    """Does the message ask for something to be written (a story, a poem...)?"""
    return bool(_COMPOSE.search(message or ""))


def run(intent, ws, level, last_answer=None):
    """Do what `intent` asks, now. file_save "after" is not done here: the
    model writes first (proxy.py), then save_new with what it wrote."""
    name, c = intent["intent"], intent.get("captures") or ()
    last_answer = without_unit_lines(last_answer)
    if name == "file_save":
        raw, folder, fmt, _when = (tuple(c) + (None,) * 4)[:4]
        rel, note = file_name(raw, fmt, last_answer)
        if folder and "/" not in rel:
            rel = "%s/%s" % (folder, rel)
        return save_new(ws, rel, last_answer or "", level, note)
    if name == "file_append":
        raw, text = (tuple(c) + (None, None))[:2]
        rel, note = file_name(raw)
        if note:
            return note.replace("so it is saved as Markdown", "and do not write into one") + \
                " Nothing was written."
        return append(ws, rel, text if text is not None else (last_answer or ""), level)
    if name == "file_write":
        raw, text = (tuple(c) + (None, None))[:2]
        rel, note = file_name(raw)
        return save_new(ws, rel, text or "", level, note)
    if name == "folder_make":
        return make_folder(ws, re.sub(r"['\"‘’“”]", "", c[0] or "").strip(" /"), level)
    if name == "file_move":
        return move(ws, c[0] or "", (c[1] or "").strip(" /"), level)
    if name == "file_delete":
        return to_trash(ws, c[0] or "", level)
    return None


def after_path(intent, text):
    """(relative name, note) for a save the unit does after the model wrote."""
    raw, folder, fmt, _when = (tuple(intent.get("captures") or ()) + (None,) * 4)[:4]
    rel, note = file_name(raw, fmt, text)
    if folder and "/" not in rel:
        rel = "%s/%s" % (folder, rel)
    return rel, note


# ---- what files she can make: said by the unit --------------------------------

_CAPABILITY = re.compile(
    r"\bwhat\s+(?:kinds?\s+of\s+|types?\s+of\s+|sorts?\s+of\s+|)files?\s+(?:can|do)\s+you\s+"
    r"(?:create|make|write|save|produce)"
    r"|\bcan\s+you\s+(?:make|create|write|save|produce|export)\s+(?:a\s+|an\s+|me\s+a\s+)?"
    r"(?:\.?(?:docx?|pdf|word|excel|xlsx|pptx?|powerpoint|markdown|md|txt|text)\b)"
    r"(?!.{0,40}\b(?:about|for|of)\b)"
    r"|\bcan\s+you\s+(?:create|make|save|write)\s+files\b"
    r"|\bwhat\s+(?:file\s+)?formats?\s+can\s+you\b", re.I | re.S)


def asks_capability(message):
    return bool(_CAPABILITY.search(message or ""))


def capability_text(level, writes_open):
    head = ("I can save text files in my workspace: Markdown (.md) and plain text (.txt). "
            "I can't make Word (.docx), PDF or other formats; a story or a list goes into a "
            ".md file, which any text editor opens.")
    how = ("\nAsk me like this:\n"
           "- \"save it as story.md\" (my last answer)\n"
           "- \"write a story about ... and save it as story.md\"\n"
           "- \"append it to story.md\"\n"
           "- \"make a folder called stories\", \"move story.md to stories\"\n"
           "- \"delete the file story.md\" (it goes to the .trash folder, and can be moved back)\n"
           "When I have written a file I say \"Saved:\" with its path. If I don't, nothing was saved.")
    if not writes_open:
        how += ("\nSaving files opens at the writer trust level, and I am at %s, "
                "so for now I can only read files." % level)
    return head + how


# ---- a claim with nothing behind it ---------------------------------------------

_CLAIM = re.compile(
    r"\b(?:saved|stored|created|moved|placed|updated|written|added)\b.{0,80}?"
    r"\b(?:file|folder|workspace|document|\.md|\.docx|\.txt|\.pdf)\b"
    r"|\bis\s+now\s+(?:in|saved|stored)\b.{0,60}?\b(?:workspace|folder|file)\b"
    r"|\b(?:i(?:'|’)?ll|i\s+will|let\s+me)\s+(?:save|store|put|move|create)\b.{0,60}?"
    r"\b(?:file|folder|workspace|document|\.md|\.docx|\.txt)\b"
    r"|\b(?:aetherseed-workspace|~/)[\w./-]+", re.I | re.S)

NOTHING_SAVED_LINE = ("\n\n(From the unit: nothing was saved for this message - no file was "
                      "written, moved or made. When I write a file I say \"Saved:\" with its path.)")


def claims_a_file_action(reply):
    return bool(_CLAIM.search(reply or ""))
