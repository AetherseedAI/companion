"""A Claude data export, brought onto the steward's own shelf.

The same as a ChatGPT export (logic/chatgpt_import.py): a collection on the
shelf, looked up only when asked, never memory. Each conversation is a
document under its own name (with its project's name in front, where the
export says which project it belongs to); each message a passage headed
"You" or "Claude". A project's own documents and its instructions come in
too, each as a document headed "Project document" or "Project instructions",
because a project is often where the work itself lives.

WHAT IS READ. conversations.json and projects.json, and nothing else of the
export. users.json (name, email, phone) is never opened. Other files are
listed by name in the preview, not read. Of each message: its words. Left
out, and counted in the preview: the assistant's thinking, tool calls and
their results, and pictures. The text of a file attached to a message (as
the export gives it) comes in as a passage of its own, headed with the
file's name, because it is the owner's own material.

THE FORMAT is read leniently: the field names below are those of Claude's
exports as known in November 2026; an export that differs is reported, not
guessed at. Checked against a real export only when one is at hand.
"""
import json
import os
import re
import zipfile
from collections import Counter
from typing import List, Tuple

from logic import chatgpt_import

TITLE = "Claude history"
MAX_ZIP = chatgpt_import.MAX_ZIP
MAX_JSON = chatgpt_import.MAX_JSON
CONVERSATIONS = re.compile(r"^(?:[^/]*/)?conversations(?:-\d+)?\.json$")
PROJECTS = re.compile(r"^(?:[^/]*/)?projects(?:-\d+)?\.json$")
NEVER = re.compile(r"(?:^|/)users?\.json$")
HIDDEN = ("thinking", "redacted_thinking")
TOOLS = ("tool_use", "tool_result", "server_tool_use", "web_search_tool_result")


def _date(s) -> str:
    s = s if isinstance(s, str) else ""
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def _open(zip_path: str):
    if os.path.getsize(zip_path) > MAX_ZIP:
        raise ValueError("that file is too large to be a Claude export I can read")
    try:
        return zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("that is not a ZIP file")


def _read_list(z, name) -> list:
    if z.getinfo(name).file_size > MAX_JSON:
        raise ValueError("%s is too large (%d MB)" % (name, z.getinfo(name).file_size // 2 ** 20))
    data = json.loads(z.read(name).decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("%s is not a list" % name)
    return [x for x in data if isinstance(x, dict)]


def _load(zip_path: str):
    """(conversations, projects, names of the files not read)."""
    z = _open(zip_path)
    names = z.namelist()
    conv_files = sorted(n for n in names if CONVERSATIONS.match(n) and not NEVER.search(n))
    proj_files = sorted(n for n in names if PROJECTS.match(n) and not NEVER.search(n))
    if not conv_files and not proj_files:
        raise ValueError("there is no conversations.json or projects.json in it: is it a Claude export?")
    convs = [c for n in conv_files for c in _read_list(z, n)]
    projects = [p for n in proj_files for p in _read_list(z, n)]
    not_read = sorted(n for n in names if n not in conv_files + proj_files and not n.endswith("/"))
    return convs, projects, not_read


def _words_of(msg: dict, left: Counter) -> List[Tuple[str, str]]:
    """[(heading suffix, words)] of one message: its text, then each attached
    file's text. What is not words is counted in `left`."""
    out = []
    parts = msg.get("content")
    words = []
    if isinstance(parts, list) and parts:
        for part in parts:
            if not isinstance(part, dict):
                continue
            t = part.get("type") or ""
            if t == "text" and isinstance(part.get("text"), str):
                words.append(part["text"])
            elif t in HIDDEN:
                left["the assistant's thinking"] += 1
            elif t in TOOLS:
                left["tool calls and their results"] += 1
            elif "image" in t:
                left["pictures"] += 1
            else:
                left["parts of other kinds (%s)" % (t or "unknown")] += 1
    if not words and isinstance(msg.get("text"), str):
        words.append(msg["text"])
    text = "\n\n".join(w.strip() for w in words if w and w.strip())
    if text:
        out.append(("", text))
    for a in msg.get("attachments") or []:
        if not isinstance(a, dict):
            continue
        body = a.get("extracted_content")
        if isinstance(body, str) and body.strip():
            out.append((" (attached file: %s)" % (a.get("file_name") or "unnamed"), body.strip()))
        else:
            left["attached files with no text in the export"] += 1
    for f in msg.get("files") or []:
        if isinstance(f, dict) and not any((a or {}).get("file_name") == f.get("file_name")
                                           for a in msg.get("attachments") or []):
            left["uploaded files (only their names are in the export)"] += 1
    return out


def _project_of(conv: dict, names: dict) -> str:
    p = conv.get("project")
    if isinstance(p, dict):
        return (p.get("name") or names.get(p.get("uuid")) or "").strip()
    return (names.get(conv.get("project_uuid")) or "").strip()


def messages(zip_path: str):
    """(the messages brought in, what was left out, one line per document,
    the files of the export not read)."""
    convs, projects, not_read = _load(zip_path)
    left, docs, out = Counter(), [], []
    names = {p.get("uuid"): (p.get("name") or "").strip() for p in projects}
    for c in convs:
        title = (c.get("name") or c.get("title") or "").strip() or "Untitled conversation"
        project = _project_of(c, names)
        if project:
            title = "%s: %s" % (project, title)
        key = c.get("uuid") or title
        n = 0
        for m in c.get("chat_messages") or []:
            if not isinstance(m, dict):
                continue
            sender = m.get("sender") or ""
            if sender not in ("human", "assistant"):
                left["messages of other senders (%s)" % (sender or "unknown")] += 1
                continue
            for suffix, text in _words_of(m, left):
                n += 1
                out.append({"conversation": key, "title": title, "date": _date(m.get("created_at") or c.get("created_at")),
                            "n": n, "who": ("You" if sender == "human" else "Claude") + suffix,
                            "role": "user" if sender == "human" else "assistant", "text": text})
        if n:
            docs.append({"title": title, "date": _date(c.get("created_at")), "messages": n})
        else:
            left["conversations with no words in them"] += 1
    for p in projects:
        pname = (p.get("name") or "").strip() or "Untitled project"
        n = 0
        key = "project-" + str(p.get("uuid") or pname)
        title = "Project: %s" % pname
        for who, text in ([("Project instructions", p.get("prompt_template"))] +
                          [("Project document: %s" % (d.get("filename") or "unnamed"), d.get("content"))
                           for d in p.get("docs") or [] if isinstance(d, dict)]):
            if isinstance(text, str) and text.strip():
                n += 1
                out.append({"conversation": key, "title": title, "date": _date(p.get("created_at")),
                            "n": n, "who": who, "role": "project", "text": text.strip()})
        if n:
            docs.append({"title": title, "date": _date(p.get("created_at")), "messages": n})
    return out, left, docs, not_read


def preview(zip_path: str) -> dict:
    """What an import would bring in, and what it would leave out. Writes nothing."""
    msgs, left, docs, not_read = messages(zip_path)
    dates = sorted(m["date"] for m in msgs if m["date"])
    return {"documents": len(docs), "messages": len(msgs),
            "conversations": sum(1 for d in docs if not d["title"].startswith("Project: ")),
            "projects": sum(1 for d in docs if d["title"].startswith("Project: ")),
            "yours": sum(1 for m in msgs if m["role"] == "user"),
            "claude": sum(1 for m in msgs if m["role"] == "assistant"),
            "project_texts": sum(1 for m in msgs if m["role"] == "project"),
            "characters": sum(len(m["text"]) for m in msgs),
            "from": dates[0] if dates else "", "to": dates[-1] if dates else "",
            "left_out": dict(left), "not_read": not_read, "titles": docs}


def preview_text(p: dict) -> str:
    lines = ["From your Claude export I would bring in %d conversations and %d projects: %d passages "
             "(%d yours, %d Claude's, %d from the projects), %s to %s."
             % (p["conversations"], p["projects"], p["messages"], p["yours"], p["claude"],
                p["project_texts"], p["from"] or "?", p["to"] or "?"),
             "It goes on your own shelf, to look up - not into memory.",
             "Claude's messages are marked as Claude's."]
    if p["left_out"]:
        lines.append("Left out:")
        lines += ["- %s: %d" % (what, n) for what, n in sorted(p["left_out"].items())]
    if p["not_read"]:
        lines.append("Not read: %s." % ", ".join(p["not_read"]))
    lines.append("Your name, email and the rest of the export are not read.")
    return "\n".join(lines)


def bring_in(zip_path: str, shelf: str = None) -> dict:
    """Bring the export onto the shelf. Returns its entry (state ready or failed)."""
    msgs, left, docs, _ = messages(zip_path)
    return chatgpt_import.shelve(msgs, left, docs, shelf, title=TITLE, source="claude-export",
                                 file_name="claude-history.jsonl", description="your Claude history")
