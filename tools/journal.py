#!/usr/bin/env python3
"""Turn the living journal on or off for one memory root (logic/journal.py).

    journal.py on  <aetherroot dir>     seed the journal (once), then use it
    journal.py off <aetherroot dir>     back to episodes; the journal stays
    journal.py status <aetherroot dir>

Run with that root's proxy STOPPED (the proxy holds the journal in memory),
as the user that owns the root.

SEEDING. A root that already has turns gets a journal written from them the
first time it is turned on: what people said to her, in order, at the time
they said it - never her answers (the point of the journal) and nothing of
the reader, the trainer or Haven (logic/journal.writes_an_entry). A journal
that is already there is never written again; turning it on twice is safe.
The turns themselves are read only, never changed: the 23 Sep 2026 rule.
Prints counts only, never words: a member's root is hers.
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from logic.journal import JOURNAL_FILE, Journal, writes_an_entry     # noqa: E402


def _set(root, mode):
    p = os.path.join(root, "config.json")
    cfg = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
    cfg["memory"] = mode
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def seed(root):
    """Write the journal from the root's turns, if it has none. Returns the
    number of entries written (0 when a journal was already there)."""
    if os.path.exists(os.path.join(root, JOURNAL_FILE)):
        return 0
    db = os.path.join(root, "memory.db")
    rows = []
    if os.path.exists(db):
        c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        try:
            cols = {r[1] for r in c.execute("pragma table_info(episodes)")}
            training = "training" in cols
            sql = "select user_msg, mode, speaker, timestamp%s from episodes order by id" % (
                ", training" if training else "")
            rows = c.execute(sql).fetchall()
        finally:
            c.close()
    from logic.speaker import label_for
    j = Journal(root, label_for=label_for)
    n = 0
    for row in rows:
        user_msg, mode, speaker, ts = row[:4]
        was_training = bool(row[4]) if len(row) > 4 else False
        if user_msg and writes_an_entry(speaker, mode, training=was_training):
            j.append(speaker or "steward", user_msg, mode=mode or "factual", at=ts)
            n += 1
    return n


def main(argv):
    if len(argv) != 3 or argv[1] not in ("on", "off", "status"):
        print(__doc__.strip().splitlines()[2:5] and __doc__)
        return 2
    what, root = argv[1], argv[2]
    if not os.path.isdir(root):
        print("no such root: %s" % root)
        return 1
    if what == "on":
        n = seed(root)
        _set(root, "journal")
    elif what == "off":
        _set(root, "episodes")
    j = Journal(root) if os.path.exists(os.path.join(root, JOURNAL_FILE)) else None
    cfg = {}
    if os.path.exists(os.path.join(root, "config.json")):
        cfg = json.load(open(os.path.join(root, "config.json"), encoding="utf-8"))
    st = j.status() if j else None
    print(json.dumps({"root": root, "memory": cfg.get("memory", "episodes"),
                      "seeded_now": n if what == "on" else None,
                      "entries": st and st["entries"], "ring_entries": st and st["ring_entries"],
                      "rings": st and st["rings"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
