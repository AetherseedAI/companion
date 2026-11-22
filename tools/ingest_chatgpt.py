#!/usr/bin/env python3
"""Bring a ChatGPT data export onto the steward's own shelf, to look up.

    sudo -u aetherseed HOME=/var/lib/aetherseed /opt/aetherseed/venv/bin/python3 \\
        /opt/aetherseed/tools/ingest_chatgpt.py preview export.zip
    ... ingest_chatgpt.py add export.zip      (shows the preview, then brings it in)
    ... ingest_chatgpt.py list
    ... ingest_chatgpt.py remove <id>         (removes exactly what the import wrote)

See logic/chatgpt_import.py for what is read and what is left out. After
"add" or "remove", restart the companion (or open the shelf in the console)
so the library sees the change.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_export  # noqa: E402


def main(argv=None):
    return ingest_export.main(argv, "chatgpt", __doc__)


if __name__ == "__main__":
    sys.exit(main())
