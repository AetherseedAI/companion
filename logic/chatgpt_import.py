"""A ChatGPT data export, brought onto the steward's own shelf.

WHAT IT BECOMES. A collection on the shelf (logic/own_shelf.py), like a
document of his: each conversation a document under its own title, each
message a passage, headed by who wrote it - "You", or "ChatGPT (gpt-4o)"
with the model that wrote it - and placed by its date. She shows it word for
word, with that source, when asked to look something up; it is never shown
unasked (the steward: "It should be a look up"). It is not memory: nothing of
it becomes something said to her or something she did. A passage of it goes
into memory only when the steward asks, with its source (logic/remember.py).

WHAT IS READ. Only conversations.json (and conversations-NNN.json where an
export is split). user.json - email, phone, birth year - is never opened, nor
any other file of the export. Of each conversation, only the branch the user
kept: from its current node back to the first message. Left out, and counted
in the preview: a conversation marked "do not remember", the assistant's
hidden thinking ("thoughts", "reasoning_recap"), messages hidden from the
conversation, tool and system messages, and pictures, audio and video (their
transcriptions come in as the words they are). The export ZIP itself is not
kept: what is kept is what was brought in, as one JSON line per message, so
the shelf holds nothing the steward did not see in the preview.

ITS OWN UNDO. The entry lists every file the import wrote; removing it from
the shelf removes those and nothing else (own_shelf.remove).
"""
import datetime
import hashlib
import json
import os
import re
import time
import zipfile
from collections import Counter
from typing import Dict, List, Tuple

from logic import own_shelf

TITLE = "ChatGPT history"
KIND = "jsonl"                               # the kept file: files/<id>.jsonl
MAX_ZIP = 2 * 1024 * 1024 * 1024             # what we open at all
MAX_JSON = 400 * 1024 * 1024                 # conversations.json, unpacked
HIDDEN_THINKING = ("thoughts", "reasoning_recap")
CONVERSATIONS = re.compile(r"^(?:[^/]*/)?conversations(?:-\d+)?\.json$")
NEVER = re.compile(r"(?:^|/)user\.json$")


def _when(t) -> str:
    try:
        return datetime.datetime.fromtimestamp(float(t), datetime.timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _load(zip_path: str) -> List[dict]:
    """The conversations of the export, and nothing else of it."""
    if os.path.getsize(zip_path) > MAX_ZIP:
        raise ValueError("that file is too large to be a ChatGPT export I can read")
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("that is not a ZIP file")
    names = sorted(n for n in z.namelist() if CONVERSATIONS.match(n) and not NEVER.search(n))
    if not names:
        raise ValueError("there is no conversations.json in it: is it a ChatGPT export?")
    out = []
    for n in names:
        if z.getinfo(n).file_size > MAX_JSON:
            raise ValueError("%s is too large (%d MB)" % (n, z.getinfo(n).file_size // 2 ** 20))
        data = json.loads(z.read(n).decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError("%s is not a list of conversations" % n)
        out.extend(c for c in data if isinstance(c, dict))
    return out


def _branch(conv: dict) -> List[dict]:
    """The messages of the branch the user kept, first to last."""
    mapping = conv.get("mapping") or {}
    node = conv.get("current_node")
    if node not in mapping:              # no current node: the deepest leaf
        leaves = [k for k, v in mapping.items() if not (v or {}).get("children")]
        node = leaves[-1] if leaves else None
    seen, chain = set(), []
    while node and node in mapping and node not in seen:
        seen.add(node)
        chain.append(mapping[node])
        node = mapping[node].get("parent")
    return [n["message"] for n in reversed(chain) if isinstance(n.get("message"), dict)]


# ChatGPT's own markup inside its answers, between private-use characters:
#   \ue200entity\ue202["people","Baruch Spinoza","dutch philosopher"]\ue201  -> Baruch Spinoza
#   \ue200cite\ue202turn0search4\ue201, \ue200filecite\ue202...\ue201, 【505†source】 -> nothing
#   \ue200url\ue202Hermes Agent\ue202https://...\ue201                         -> Hermes Agent
#   \ue200genui\ue202{... "content":"\\frac{dx}{dt} ..."}\ue201              -> the formula
# Counted in the preview. Found in the first real export: 451 entities,
# 76 citations, 19 source marks, 10 formulas, 1 link (3 Nov 2026); left in,
# their brackets kept 216 messages from being kept in memory whole.
_MARK = re.compile("\ue200(\\w+)\ue202(.*?)\ue201", re.S)
_SOURCE_MARK = re.compile("【[^】]{0,80}】")
_PUA = re.compile("[\ue000-\uf8ff]")


def _unmark(text: str, left: Counter) -> str:
    def one(m):
        kind, body = m.group(1), m.group(2)
        left["ChatGPT's link and citation marks (the words they name are kept)"] += 1
        if kind == "entity":
            try:
                parts = json.loads(body)
                return str(parts[1]) if isinstance(parts, list) and len(parts) > 1 else ""
            except ValueError:
                return ""
        if kind == "url":
            return body.split("\ue202")[0]
        if kind == "genui":
            hit = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
            if hit:
                try:
                    return json.loads('"%s"' % hit.group(1))
                except ValueError:
                    return ""
            return ""
        return ""                                   # cite, filecite and the rest
    text = _MARK.sub(one, text)
    n = len(_SOURCE_MARK.findall(text))
    if n:
        left["ChatGPT's link and citation marks (the words they name are kept)"] += n
        text = _SOURCE_MARK.sub("", text)
    return _PUA.sub("", text)


def _text_of(msg: dict, left: Counter) -> str:
    """The words of a message; what is not words is counted in `left`."""
    content = msg.get("content") or {}
    ctype = content.get("content_type")
    if ctype in HIDDEN_THINKING:
        left["the assistant's hidden thinking"] += 1
        return ""
    if ctype not in ("text", "multimodal_text"):
        left["messages of other kinds (%s)" % (ctype or "unknown")] += 1
        return ""
    words = []
    for part in content.get("parts") or []:
        if isinstance(part, str):
            words.append(part)
        elif isinstance(part, dict):
            pt = part.get("content_type") or ""
            if pt == "audio_transcription" and isinstance(part.get("text"), str):
                words.append(part["text"])
            elif "image" in pt:
                left["pictures"] += 1
            elif "audio" in pt or "video" in pt:
                left["audio or video recordings (their words, where transcribed, are kept)"] += 1
            else:
                left["parts of other kinds"] += 1
    text = "\n\n".join(w.strip() for w in words if w and w.strip())
    if ((msg.get("author") or {}).get("role")) == "assistant":
        text = _unmark(text, left)
    return text


def messages(zip_path: str) -> Tuple[List[dict], Counter, List[dict]]:
    """(the messages brought in, what was left out, one line per conversation)."""
    left, convs, out = Counter(), [], []
    for c in _load(zip_path):
        title = (c.get("title") or "").strip() or "Untitled conversation"
        if c.get("is_do_not_remember"):
            left['conversations marked "do not remember"'] += 1
            continue
        n = 0
        for m in _branch(c):
            role = ((m.get("author") or {}).get("role")) or ""
            md = m.get("metadata") or {}
            if role not in ("user", "assistant"):
                if role:
                    left["system and tool messages"] += 1
                continue
            if md.get("is_visually_hidden_from_conversation"):
                left["messages hidden from the conversation"] += 1
                continue
            text = _text_of(m, left)
            if not text:
                continue
            who = "You" if role == "user" else "ChatGPT (%s)" % (md.get("model_slug") or "model not named")
            n += 1
            out.append({"conversation": c.get("conversation_id") or c.get("id") or title,
                        "title": title, "date": _when(m.get("create_time") or c.get("create_time")),
                        "n": n, "who": who, "role": role, "text": text})
        if n:
            convs.append({"title": title, "date": _when(c.get("create_time")), "messages": n})
        else:
            left["conversations with no words in them"] += 1
    return out, left, convs


def preview(zip_path: str) -> dict:
    """What an import would bring in, and what it would leave out. Writes nothing."""
    msgs, left, convs = messages(zip_path)
    dates = sorted(m["date"] for m in msgs if m["date"])
    return {"conversations": len(convs), "messages": len(msgs),
            "yours": sum(1 for m in msgs if m["role"] == "user"),
            "chatgpt": sum(1 for m in msgs if m["role"] == "assistant"),
            "characters": sum(len(m["text"]) for m in msgs),
            "from": dates[0] if dates else "", "to": dates[-1] if dates else "",
            "models": dict(Counter(m["who"] for m in msgs if m["role"] == "assistant").most_common()),
            "left_out": dict(left), "titles": convs}


def preview_text(p: dict) -> str:
    lines = ["From your ChatGPT export I would bring in %d conversations, %d messages "
             "(%d yours, %d ChatGPT's), %s to %s." % (p["conversations"], p["messages"], p["yours"],
                                                      p["chatgpt"], p["from"] or "?", p["to"] or "?"),
             "It goes on your own shelf, to look up - not into memory.",
             "ChatGPT's messages are marked as ChatGPT's, with the model that wrote them."]
    if p["left_out"]:
        lines.append("Left out:")
        lines += ["- %s: %d" % (what, n) for what, n in sorted(p["left_out"].items())]
    lines.append("Your email, phone and the rest of the export are not read.")
    return "\n".join(lines)


def bring_in(zip_path: str, shelf: str = None) -> dict:
    """Bring the export onto the shelf. Returns its entry (state ready or
    failed). Nothing is written if there is nothing to bring in."""
    msgs, left, convs = messages(zip_path)
    return shelve(msgs, left, convs, shelf, title=TITLE, source="chatgpt-export",
                  file_name="chatgpt-history.jsonl", description="your ChatGPT history")


def shelve(msgs, left, convs, shelf=None, title=TITLE, source="chatgpt-export",
           file_name="chatgpt-history.jsonl", description="your ChatGPT history") -> dict:
    """The messages of an export (this one's, or another assistant's: see
    logic/claude_import.py) onto the shelf as one asked-only collection."""
    shelf = shelf or own_shelf.SHELF_DIR
    if not msgs:
        raise ValueError("there are no messages in it that I can read")
    kept_lines = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs).encode("utf-8")
    digest = hashlib.sha256(kept_lines).hexdigest()
    own_shelf.converter()             # loaded before anything is written: none, nothing written
    with own_shelf._lock:
        have = own_shelf.listing(shelf)
        for e in have:
            if e.get("sha256") == digest and e.get("state") != own_shelf.FAILED:
                raise ValueError('I already have that history: "%s".' % e.get("title", e["id"]))
        if len(have) >= own_shelf.MAX_DOCUMENTS:
            raise ValueError("the shelf is full (%d documents). Remove one first." % own_shelf.MAX_DOCUMENTS)
        doc_id = own_shelf.make_id(file_name, {e["id"] for e in have})
        os.makedirs(os.path.join(shelf, "files"), mode=0o750, exist_ok=True)
        kept, meta_path, coll = own_shelf._paths(shelf, doc_id, "." + KIND)
        fd = os.open(kept, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
        with os.fdopen(fd, "wb") as f:
            f.write(kept_lines)
        added = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        entry = {"id": doc_id, "title": title, "kind": KIND, "bytes": len(kept_lines),
                 "sha256": digest, "added": added, "state": own_shelf.READING,
                 "pages": None, "passages": None, "note": "", "source": source,
                 "description": description,
                 "asked_only": True, "conversations": len(convs), "messages": len(msgs),
                 "left_out": dict(left),
                 # its own undo: every file this import wrote, and nothing else
                 "wrote": [os.path.relpath(p, shelf) for p in (kept, meta_path, coll)]}
        own_shelf._write_entry(shelf, entry)
    return build(entry, msgs, shelf)


def build(entry: dict, msgs: List[dict] = None, shelf: str = None) -> dict:
    """Make the entry's collection from the messages - or, given none, from
    the kept file: a start in the middle of an import reads it again."""
    shelf = shelf or own_shelf.SHELF_DIR
    lb = own_shelf.converter()
    kept, _, coll = own_shelf._paths(shelf, entry["id"], "." + KIND)
    doc_id = entry["id"]
    if msgs is None:
        with open(kept, encoding="utf-8") as f:
            msgs = [json.loads(l) for l in f if l.strip()]
    kept_lines_len, digest, added = entry["bytes"], entry["sha256"], entry["added"]
    tmp = coll + ".tmp"
    try:
        db = lb.fresh(tmp)
        docs: Dict[str, int] = {}
        seq: Counter = Counter()
        n = 0
        for m in msgs:
            key = m["conversation"]
            if key not in docs:
                cur = db.execute("INSERT INTO docs(title, author, locator, note) VALUES (?,?,?,?)",
                                 (m["title"], "", "%s#%s" % (doc_id, key), m["date"]))
                docs[key] = cur.lastrowid
            paras = [p.strip() for p in re.split(r"\n\s*\n", m["text"].replace("\r", "")) if p.strip()]
            for piece in lb.passages_from(paras):
                seq[key] += 1
                n += 1
                lb.add(db, docs[key], seq[key], m["title"], m["who"],
                       "%s, message %d" % (m["date"], m["n"]) if m["date"] else "message %d" % m["n"],
                       piece)
        lb.finish(db, {"id": "own-" + doc_id, "title": entry.get("title") or TITLE, "own": "1",
                       "asked_only": "1", "description": entry.get("description") or "your ChatGPT history", "date": added[:10], "language": "",
                       "kind": "documents", "creator": "", "publisher": "",
                       "licence": "the steward's own history", "source_file": doc_id + "." + KIND,
                       "source_bytes": str(kept_lines_len), "source_sha256": digest})
        os.replace(tmp, coll)
        entry.update(state=own_shelf.READY, passages=n)
    except Exception as e:                       # never leave a half-made collection listed as ready
        entry.update(state=own_shelf.FAILED, note=("it could not be read (%s)" % type(e).__name__)[:200])
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    with own_shelf._lock:
        own_shelf._write_entry(shelf, entry)
    return entry
