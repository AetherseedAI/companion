#!/usr/bin/env python3
"""One file that holds a unit's memory, readable without this software.

    sudo -u aetherseed HOME=/var/lib/aetherseed /opt/aetherseed/venv/bin/python3 \\
        /opt/aetherseed/tools/export.py --out /var/lib/aetherseed/export.jsonl

Asked for by the steward with the research of 29 Oct 2026: her data must
outlive the model and the code. The file is JSON Lines - one JSON object a
line, text in UTF-8 - which any editor opens and any language reads. Line 1
says what the file is and what each kind of line holds. Then:

  {"kind": "table", "table": T, "row": {...}}   every row of every table of
        her memory (memory.db): her turns, rings, the steward's facts and notes,
        her identity and growth. A column of bytes (a turn's word vector) is
        left out: it is made again from the text, and says nothing to a reader.
  {"kind": "file", "path": P, "text": "..."}    every text file of her state
        (~/.aetherseed: the logs and their chain, the trust record, the
        corrections) and of her workspace (the to-do list, notes, folders).
  {"kind": "left_out", "path": P, "bytes": N, "why": "..."}   what is not in it.

Left out always: passkeys and tokens, and files of numbers made from the
text (the meaning index, vectors). Left out unless --all: the prompt logs
(what was sent to the model - large, and made from the rest) and the
training record. Nothing is changed; the database is read through a
read-only connection.
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys

FORMAT = 1
NEVER = (".token", ".npz", ".npy", ".last-read", "-shm", "-wal", ".pyc")
NEVER_NAMES = ("passkey", "steward_key", "secret")
UNLESS_ALL = ("prompts-",)
UNLESS_ALL_DIRS = ("training",)


def header(name, home):
    return {
        "kind": "aetherseed-export", "format": FORMAT,
        "made_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "companion": name, "home": home,
        "lines": {
            "table": "one row of her memory database: table name and the row's columns",
            "file": "one text file of her state or workspace: its path and its text",
            "left_out": "a file not in this export, and why",
            "end": "the last line: how many lines of each kind came before it",
        },
    }


def _why_not(rel, include_all):
    base = os.path.basename(rel)
    low = base.lower()
    if low.endswith(NEVER) or any(n in low for n in NEVER_NAMES):
        return "a secret, or numbers made from the text"
    if low.endswith(".db") or ".db-" in low or low.endswith((".sqlite", ".safetensors")):
        return "a database or model file (her memory database is exported as its tables)"
    if not include_all:
        if base.startswith(UNLESS_ALL):
            return "a prompt log (use --all)"
        if rel.split(os.sep)[0] in UNLESS_ALL_DIRS or \
                (len(rel.split(os.sep)) > 1 and rel.split(os.sep)[1] in UNLESS_ALL_DIRS):
            return "the training record (use --all)"
    return None


def tables(db_path):
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]
        for t in names:
            cur = con.execute('SELECT * FROM "%s"' % t.replace('"', '""'))
            cols = [d[0] for d in cur.description]
            for row in cur:
                yield t, {c: v for c, v in zip(cols, row) if not isinstance(v, (bytes, memoryview))}
    finally:
        con.close()


def files(root, prefix, include_all):
    for dirpath, dirs, names in os.walk(root):
        dirs.sort()
        for fn in sorted(names):
            full = os.path.join(dirpath, fn)
            rel = os.path.join(prefix, os.path.relpath(full, root))
            if os.path.islink(full):
                yield {"kind": "left_out", "path": rel, "bytes": 0, "why": "a link"}
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            why = _why_not(os.path.relpath(full, root), include_all)
            if why:
                yield {"kind": "left_out", "path": rel, "bytes": size, "why": why}
                continue
            try:
                with open(full, "rb") as f:
                    text = f.read().decode("utf-8")
            except UnicodeDecodeError:
                yield {"kind": "left_out", "path": rel, "bytes": size, "why": "not text"}
                continue
            except OSError as e:
                yield {"kind": "left_out", "path": rel, "bytes": size, "why": "unreadable: %s" % e.strerror}
                continue
            yield {"kind": "file", "path": rel, "text": text}


def export(home, out, include_all=False):
    state = os.path.join(home, ".aetherseed")
    try:
        name = json.load(open(os.path.join(state, "companion.json"), encoding="utf-8")).get("name")
    except (OSError, ValueError):
        name = None
    counts = {}
    with open(out, "w", encoding="utf-8") as f:
        def put(obj):
            counts[obj["kind"]] = counts.get(obj["kind"], 0) + 1
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.write(json.dumps(header(name, home), ensure_ascii=False) + "\n")
        db = os.path.join(state, "aetherroot", "memory.db")
        if os.path.exists(db):
            for t, row in tables(db):
                put({"kind": "table", "table": t, "row": row})
        for root, prefix in ((state, ".aetherseed"),
                             (os.path.join(home, "aetherseed-workspace"), "aetherseed-workspace")):
            if os.path.isdir(root):
                for obj in files(root, prefix, include_all):
                    if os.path.abspath(os.path.join(home, obj["path"])) == os.path.abspath(out):
                        continue
                    put(obj)
        f.write(json.dumps({"kind": "end", "counts": counts}) + "\n")
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--home", default=os.path.expanduser("~"))
    ap.add_argument("--all", action="store_true", help="also the prompt logs and the training record")
    a = ap.parse_args()
    counts = export(a.home, a.out, a.all)
    print("written: %s (%s)" % (a.out, ", ".join("%s %d" % kv for kv in sorted(counts.items()))))


if __name__ == "__main__":
    sys.exit(main())
