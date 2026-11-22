#!/usr/bin/env python3
"""Build her meaning index (logic/semantic_index.py) for every stored turn.

    sudo -u aetherseed python3 tools/semantic_index.py            what is missing
    sudo -u aetherseed python3 tools/semantic_index.py --build    and build it

Needs the embedding model (logic/embed.py). Reads memory.db, writes
semantic.npz beside it; changes nothing else. On a unit about 0.7 s a turn:
run it with the proxy stopped, or between turns, and it can be stopped and run
again - it saves every 100 turns and goes on where it left off.
"""
import argparse
import os
import sqlite3
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from logic import embed  # noqa: E402
from logic.semantic_index import SemanticIndex  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--root", default=os.path.expanduser("~/.aetherseed/aetherroot"))
    a = ap.parse_args(argv)
    e = embed.shared()
    if e is None:
        print("the embedding model is not installed (logic/embed.py)")
        return 1
    idx = SemanticIndex(a.root, e)
    db = sqlite3.connect("file:%s?mode=ro" % os.path.join(a.root, "memory.db"), uri=True)
    rows = [r for r in db.execute("SELECT id, user_msg FROM episodes ORDER BY id") if not idx.has(r[0])]
    print("%d turns indexed, %d missing" % (len(idx), len(rows)))
    if not a.build:
        return 0
    t = time.time()
    for n, (i, text) in enumerate(rows, 1):
        idx.add(i, text, save=False)
        if n % 100 == 0:
            idx.save()
            print("  %d of %d, %.0f s" % (n, len(rows), time.time() - t), flush=True)
    idx.save()
    print("done: %d turns indexed" % len(idx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
