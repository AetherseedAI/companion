"""The command behind ingest_chatgpt.py and ingest_claude.py: an assistant's
data export onto the steward's own shelf, to look up. One command, two
readers (logic/chatgpt_import.py, logic/claude_import.py)."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logic import chatgpt_import, claude_import, own_shelf  # noqa: E402

# kind: (reader, the shelf entry's source, the assistant's name, what a title counts)
KINDS = {
    "chatgpt": (chatgpt_import, "chatgpt-export", "ChatGPT", "messages"),
    "claude": (claude_import, "claude-export", "Claude", "passages"),
}


def main(argv, kind, doc):
    reader, source, name, counted = KINDS[kind]
    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shelf", default=None, help="the shelf directory (default: the steward's own)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("preview", "add"):
        p = sub.add_parser(cmd)
        p.add_argument("zip")
        p.add_argument("--titles", action="store_true", help="also list the conversations")
    sub.add_parser("list")
    sub.add_parser("remove").add_argument("id")
    a = ap.parse_args(argv)
    try:
        if a.cmd in ("preview", "add"):
            p = reader.preview(a.zip)
            print(reader.preview_text(p))
            if a.titles:
                for t in p["titles"]:
                    print("  %s  %s (%d %s)" % (t["date"], t["title"], t["messages"], counted))
            if a.cmd == "add":
                e = reader.bring_in(a.zip, a.shelf)
                print("\n%s: %s, %s passages." % (e["id"], e["state"], e.get("passages")))
                if e.get("note"):
                    print(e["note"])
                return 0 if e["state"] == own_shelf.READY else 1
        elif a.cmd == "list":
            for e in own_shelf.listing(a.shelf):
                if e.get("source") == source:
                    print("%s  %s  %s  %s conversations, %s passages" % (
                        e["id"], e["added"][:10], e["state"], e.get("conversations"), e.get("passages")))
        elif a.cmd == "remove":
            e = next((x for x in own_shelf.listing(a.shelf) if x["id"] == a.id), None)
            if not e or e.get("source") != source:
                print("No %s history with that id on the shelf." % name)
                return 1
            print("Removed." if own_shelf.remove(a.id, a.shelf) else "Not removed.")
    except (ValueError, OSError) as e:
        print("I could not read it: %s" % e)
        return 1
    return 0
