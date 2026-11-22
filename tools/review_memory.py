#!/usr/bin/env python3
"""Corrections from a review of her memory that the steward asked for.

    sudo -u aetherseed python3 tools/review_memory.py corrections.json --reviewer NAME
    sudo -u aetherseed python3 tools/review_memory.py corrections.json --reviewer NAME --apply

corrections.json: a list of {"target": "turn"|"ring", "id": N, "reason":
"part"|"detail"|"about"|"never", "text": "what is true"}.

Each is the console's guided correction (logic/steward.py), attributed to the
review: the turn or ring comes back to her tagged "[Corrected in a review your
steward asked for - what is true: ...]", nothing is deleted, the steward can
undo any of them from the console, and each is a line in corrections.log with
the reviewer's name. What is true is not kept as one of the steward's facts:
he did not write it. Dry run unless --apply. Stop the proxy first, so the
chained log has one writer.
"""
import argparse
import json
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from aetherroot import MemoryStore  # noqa: E402
from logic import steward  # noqa: E402

HOME = os.path.expanduser("~/.aetherseed")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default=os.path.join(HOME, "aetherroot", "memory.db"))
    ap.add_argument("--log", default=os.path.join(HOME, "corrections.log"))
    a = ap.parse_args(argv)
    items = json.load(open(a.file, encoding="utf-8"))
    store = MemoryStore(a.db)
    ok = 0
    for it in items:
        target, tid = it["target"], int(it["id"])
        try:
            if target == "turn":
                row = store.conn.execute("SELECT substr(user_msg,1,60), substr(ai_msg,1,80) "
                                         "FROM episodes WHERE id = ?", (tid,)).fetchone()
            else:
                row = store.conn.execute("SELECT ring_no, substr(own_words,1,80) FROM semantic "
                                         "WHERE id = ?", (tid,)).fetchone()
            if row is None:
                print("%s %d: not found" % (target, tid)); continue
            print("%s %d: %s | %s\n    -> %s: %s" % (target, tid, row[0], row[1], it["reason"], it.get("text", "")))
            if a.apply:
                steward.correct(store, target, tid, it["reason"], it.get("text", ""),
                                log_path=a.log, by=steward.REVIEW, reviewer=a.reviewer)
                ok += 1
        except steward.StewardError as e:
            print("    not applied: %s" % e)
    print("%s %d of %d" % ("applied" if a.apply else "dry run, would apply", ok if a.apply else len(items), len(items)))


if __name__ == "__main__":
    main()
