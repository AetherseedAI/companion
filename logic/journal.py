"""The living journal: what was said to her, kept in a file that is hers.

WHY (plan-living-journal, 14 Nov 2026). Read on a unit's store: of 9,045
turns 98 % were the reader's and the trainer's, 186 her steward's; 106 of her
stored answers named a model she no longer ran, and on the new model she gave
that answer word for word; one answer of hers to "Can you focus?" came back
as the answer to "Can animals actually suffer?" seven times. A turn came back
as `question | AI: her answer`, and what follows "AI:" is what a small model
writes next. Her own old answers were the strongest voice in her prompt.

THE JOURNAL. `journal.md` in her state folder, one entry a line, only ever
added to:

    - #17 · 2026-11-14T10:12:03+00:00 · steward · - · said: <the words> · she: answered

AN ENTRY HOLDS WHAT WAS SAID TO HER, NOT WHAT SHE ANSWERED: the person's
words, who said them, and what she did, as the unit knows it ("answered",
"wrote something made up, as asked"). Her reply is not in it, so it cannot
come back to be copied. Her recent words still reach her as the conversation
in progress (logic/working_memory.py), and nowhere else.

WHO WRITES ONE. The people she lives with. A reader, a trainer or a test
harness writes none (NOT_PEOPLE; training turns; reflections): they keep
their own records, and they were 98 % of the store this replaces.

RINGS, BY COUNTING. Every 12th entry closes a RING ENTRY; every 20th ring
entry closes a FULL RING (240 entries). Both are made by code from the
entries' own words - the most distinctive words and one quote
(logic/rings.py: themes, ring_content) - so nothing in a ring can be
invented. They are lines in `rings.md`, added once, in order:

    - e2 · #13-#24 · <time> · themes: ... · e.g. Steward: “...”
    = r1 · e1-e20 · <time> · themes: ... · e.g. Steward: “...”

Only plain-fact entries that are not private count toward a ring, as before:
a story is not what she knows, and a ring is something a partner may be
shown. How many ring lines there should be follows from the journal alone,
so a power cut between the two files is made up at the next start (_grow).

WHAT COMES BACK. The last CYCLE entries, the last twenty ring entries and
every full ring are what a question is matched against, by its words, as
turns were (aetherroot.retrieve_context). There is no search by meaning.

NEVER REWRITTEN. Both files are opened for appending only and fsynced. A
half-written last line (a power cut) is left where it is and not read.
"""
import os
import threading
from datetime import datetime, timezone

ENTRIES_PER_RING_ENTRY = 12
RING_ENTRIES_PER_RING = 20
CYCLE = ENTRIES_PER_RING_ENTRY * RING_ENTRIES_PER_RING     # 240
SAID_MAX = 280
JOURNAL_FILE = "journal.md"
RINGS_FILE = "rings.md"
SEP = " · "
# Speakers that are not people she lives with (lower case).
NOT_PEOPLE = frozenset({"reader", "trainer", "haven", "claude"})
FLAGS = ("private", "fiction", "unverified")
DID = {
    "factual": "answered",
    "fiction": "wrote something made up, as asked",
    "unverified": "answered; what she said was not verified",
}


def writes_an_entry(speaker, mode, training=False):
    """Does a turn of this speaker go into the journal?"""
    if training or (mode or "") == "cog":
        return False
    return (speaker or "").strip().lower() not in NOT_PEOPLE


def _one_line(text, limit):
    text = " ".join((text or "").replace("·", "-").split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"
    return text


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path, line):
    """One line added to the end, on disk before we return. Never a rewrite."""
    new = not os.path.exists(path)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        if not new and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    os.write(fd, b"\n")        # after a half-written line
        os.write(fd, (line + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def parse_entry(line):
    """An entry line as a dict, or None for anything else (a heading, a
    half-written line)."""
    if not line.startswith("- #"):
        return None
    parts = line.rstrip("\n").split(SEP)
    if len(parts) != 6 or not parts[4].startswith("said: ") or not parts[5].startswith("she: "):
        return None
    try:
        n = int(parts[0][3:])
    except ValueError:
        return None
    flags = set() if parts[3] == "-" else set(parts[3].split(","))
    mode = "fiction" if "fiction" in flags else "unverified" if "unverified" in flags else "factual"
    return {"n": n, "at": parts[1], "speaker": parts[2], "private": "private" in flags,
            "mode": mode, "said": parts[4][6:], "did": parts[5][5:]}


def parse_ring(line):
    """A ring line as a dict: kind "entry" (- eN) or "ring" (= rN)."""
    line = line.rstrip("\n")
    if line.startswith("- e"):
        kind = "entry"
    elif line.startswith("= r"):
        kind = "ring"
    else:
        return None
    parts = line.split(SEP, 3)
    if len(parts) != 4:
        return None
    try:
        no = int(parts[0][3:])
    except ValueError:
        return None
    return {"kind": kind, "no": no, "span": parts[1], "at": parts[2], "content": parts[3]}


class Journal:
    """Her journal and its rings, in `folder`. One writer (the proxy)."""

    def __init__(self, folder, label_for=None):
        self.folder = str(folder)
        self.path = os.path.join(self.folder, JOURNAL_FILE)
        self.rings_path = os.path.join(self.folder, RINGS_FILE)
        self.label_for = label_for or (lambda s: (s or "Someone").capitalize())
        self._lock = threading.RLock()
        self.entries, self.ring_entries, self.rings = [], [], []
        self._load()
        with self._lock:
            self._grow()

    # ---- reading ---------------------------------------------------------------

    def _load(self):
        self.entries, self.ring_entries, self.rings = [], [], []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    e = parse_entry(line)
                    if e:
                        self.entries.append(e)
        if os.path.exists(self.rings_path):
            with open(self.rings_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    r = parse_ring(line)
                    if r:
                        (self.ring_entries if r["kind"] == "entry" else self.rings).append(r)

    def _countable(self):
        """The entries a ring is made of: not made up, not private. (An entry
        flagged unverified counts: the flag was about her answer, and the
        entry holds only what the person said.)"""
        return [e for e in self.entries if e["mode"] != "fiction" and not e["private"]]

    # ---- writing ---------------------------------------------------------------

    def append(self, speaker, said, mode="factual", private=False, did=None, at=None):
        """One entry for what `speaker` said. Returns its number."""
        flags = [f for f, on in (("private", private), ("fiction", mode == "fiction"),
                                 ("unverified", mode == "unverified")) if on]
        with self._lock:
            n = (self.entries[-1]["n"] + 1) if self.entries else 1
            entry = {"n": n, "at": at or _now(),
                     "speaker": _one_line(speaker or "someone", 40) or "someone",
                     "private": bool(private),
                     "mode": mode if mode in ("fiction", "unverified") else "factual",
                     "said": _one_line(said, SAID_MAX),
                     "did": _one_line(did or DID.get(mode, "answered"), 80)}
            if not os.path.exists(self.path):
                _append(self.path, "# Journal")
            _append(self.path, SEP.join([
                "- #%d" % n, entry["at"], entry["speaker"], ",".join(flags) or "-",
                "said: " + entry["said"], "she: " + entry["did"]]))
            self.entries.append(entry)
            self._grow()
            return n

    def _content(self, batch):
        """Themes and one quote of `batch`: every word in it was said to her."""
        from logic.rings import themes, tokens, ring_content
        count = self._countable()
        df = {}
        for e in count:
            for t in set(tokens(e["said"])):
                df[t] = df.get(t, 0) + 1
        words = themes([e["said"] for e in batch], df, len(count) or 1)
        best, best_score = batch[0], -1
        for e in batch:                       # the entry holding most of the themes
            score = len(set(tokens(e["said"])) & set(words))
            if score > best_score:
                best, best_score = e, score
        return ring_content(words, self.label_for(best["speaker"]), best["said"])

    def _grow(self):
        """Close what is due: a ring entry per 12 countable entries, a ring per
        20 ring entries. Follows from the journal alone, so it also makes up
        what a power cut left unwritten."""
        count = self._countable()
        while len(self.ring_entries) < len(count) // ENTRIES_PER_RING_ENTRY:
            k = len(self.ring_entries) + 1
            batch = count[(k - 1) * ENTRIES_PER_RING_ENTRY:k * ENTRIES_PER_RING_ENTRY]
            r = {"kind": "entry", "no": k, "span": "#%d-#%d" % (batch[0]["n"], batch[-1]["n"]),
                 "at": batch[-1]["at"], "content": self._content(batch)}
            if not os.path.exists(self.rings_path):
                _append(self.rings_path, "# Rings")
            _append(self.rings_path, SEP.join(["- e%d" % k, r["span"], r["at"], r["content"]]))
            self.ring_entries.append(r)
        while len(self.rings) < len(self.ring_entries) // RING_ENTRIES_PER_RING:
            k = len(self.rings) + 1
            batch = count[(k - 1) * CYCLE:k * CYCLE]
            r = {"kind": "ring", "no": k,
                 "span": "e%d-e%d" % ((k - 1) * RING_ENTRIES_PER_RING + 1, k * RING_ENTRIES_PER_RING),
                 "at": batch[-1]["at"], "content": self._content(batch)}
            _append(self.rings_path, SEP.join(["= r%d" % k, r["span"], r["at"], r["content"]]))
            self.rings.append(r)

    # ---- for a prompt ----------------------------------------------------------

    def recent(self, only_speaker=None, exclude_private=False):
        """The entries a question is matched against: all of them. (A window
        of the last CYCLE was tried first, 14 Nov: the dog's name, told on
        the first day, fell out of it after 240 entries and she named the
        boat instead - a ring keeps themes, not facts.)"""
        with self._lock:
            out = list(self.entries)
        if only_speaker is not None:
            out = [e for e in out if e["speaker"] == only_speaker]
        if exclude_private:
            out = [e for e in out if not e["private"]]
        return out

    def recent_ring_entries(self):
        with self._lock:
            return list(self.ring_entries[-RING_ENTRIES_PER_RING:])

    def all_rings(self):
        with self._lock:
            return list(self.rings)

    def entry_line(self, e):
        """An entry as she is shown it: who said what, when, and what she did.
        Never what she answered."""
        # What she did is kept in the file and left out here: "(she
        # answered)" was said back at the end of 3 answers of 40 (14 Nov).
        made_up = " - you wrote something made up" if e["mode"] == "fiction" else ""
        return "[Journal] %s · %s said: %s%s" % (
            e["at"][:10], self.label_for(e["speaker"]), e["said"], made_up)

    def status(self):
        with self._lock:
            count = len(self._countable())
            return {"entries": len(self.entries), "ring_entries": len(self.ring_entries),
                    "rings": len(self.rings),
                    "into": count % ENTRIES_PER_RING_ENTRY, "of": ENTRIES_PER_RING_ENTRY,
                    "last_at": self.entries[-1]["at"] if self.entries else None}

    def text(self):
        """Both files as they stand, for the console (read-only)."""
        out = {}
        for key, path in (("journal", self.path), ("rings", self.rings_path)):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    out[key] = f.read()
            except OSError:
                out[key] = ""
        return out
