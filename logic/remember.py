"""A passage from the library, kept in her memory when the steward asks.

The steward, 1 Nov 2026: "The look up should have an add to memory function
and button/command. So if you come across information you want from the
shelf or library you can add that in the moment to memory."

WHAT IS KEPT. The passage she just showed - from his ChatGPT history, his
own documents, Wikipedia or a manual - word for word, as a steward fact
(logic/facts.py): it comes back as "[Steward told you] ..." with where it is
from, so it is never something she knows of herself, and never something
she said or lived. Its lines are joined into one: a fact is one line. A
kept passage may be longer than a fact - up to KEPT_MAX_CHARS, a whole
passage of the library (the steward chose "a larger kept slot", 3 Nov 2026).
Asked about later ("What do you know about X?") it is said back by the unit,
word for word with its source; one longer than a fact is not put in the
prompt (see below for what the model did with it). One longer than that,
or with brackets or pipes in it, is not cut or rewritten to fit: she says
so, and the steward can keep the part he wants in his own words ("Remember
that I ..." goes to the steward file; logic/steward_file.py).

WHEN. Only when asked ("remember that", "add that to memory", "husk det"),
and only the passage on the screen, within MAX_AGE of being shown. Never on
her own, and she does not offer to. Only the steward, and from the writer
level up (it changes her memory, as a to-do does). Not in a lesson.

ITS UNDO. "Forget that", as his very next message, takes the kept passage
out again (revoked, as tools/steward_facts.py does), instead of his last
turn. Both are lines in corrections.log, as every fact change is.
"""
import re

from logic.facts import MAX_SOURCE_CHARS

MAX_AGE = 900          # seconds: the passage "on the screen"
# A kept passage may be longer than a fact (MAX_FACT_CHARS): a passage of the
# library is up to 900 characters, and the steward chose "a larger kept slot"
# (3 Nov 2026) over cutting the history smaller. It comes back whole, said by
# the unit (recalled, below).
KEPT_MAX_CHARS = 900
_FORBIDDEN = ("[", "]", "<|", "|>", "|")

ASKS = re.compile(
    r"^\s*(?:(?:please|ok(?:ay)?|yes)[,\s]+)*(?:"
    r"(?:remember|keep|save|store)\s+(?:that|this|it)(?:\s+(?:passage|one))?(?:\s+(?:for\s+me|in\s+(?:your\s+)?memory))?"
    r"|add\s+(?:that|this|it)(?:\s+passage)?\s+to\s+(?:your\s+)?memory"
    r"|husk\s+(?:det|dette)(?:\s+for\s+meg)?"
    r"|legg\s+(?:det|dette)\s+(?:til\s+)?i\s+minnet(?:\s+ditt)?"
    r")\s*(?:,?\s*please)?\s*[.!]*\s*$", re.I)

NOTHING_SHOWN = ("There is no passage on the screen for me to keep. Ask me to look "
                 "something up first, then say \"remember that\".")
NOT_A_GUEST = "Only my steward can add to my memory."
NOT_IN_A_LESSON = "In training I do not add to my memory."


def asks(text: str) -> bool:
    return bool(ASKS.match(text or ""))


def source_of(hit: dict) -> str:
    """Where it is from, in at most MAX_SOURCE_CHARS: "ChatGPT (gpt-4o),
    2024-11-29", "Wikipedia: Photosynthesis", "your document: Notes"."""
    if hit.get("history"):
        # with the conversation's title: "Hva vet du om hagen om våren?"
        # missed a kept passage that never says the words of its title
        # (ChatGPT-shelf soak 4, 3 Nov 2026) - the source is indexed too
        date = (hit.get("place") or "").split(",")[0]
        app = _app_of(hit)
        who = "you in %s" % app if hit.get("heading") == "You" else (hit.get("heading") or app)
        s = ", ".join(x for x in (who, date) if x)
        if hit.get("title"):
            s += ": " + hit["title"]
    elif hit.get("own"):
        s = "your document: %s" % hit.get("title", "")
    else:
        coll = re.sub(r"\s*\(\d{4}-\d{2}\)\s*$", "", hit.get("collection") or "library")
        s = "%s: %s" % (coll, hit.get("title", ""))
    s = " ".join(s.split()).replace("[", "(").replace("]", ")").replace("|", "/")
    return s if len(s) <= MAX_SOURCE_CHARS else s[:MAX_SOURCE_CHARS - 1].rstrip() + "…"


def _app_of(hit: dict) -> str:
    """The assistant a history is from: "ChatGPT history" -> "ChatGPT"."""
    return re.sub(r"\s+history\s*$", "", hit.get("collection") or "", flags=re.I) or "ChatGPT"


def text_of(hit: dict) -> str:
    """The passage as one line: its words, in order, nothing changed but the
    breaks between its lines."""
    return " ".join((hit.get("text") or "").split())


def why_not(hit: dict):
    """(text, source, None) if the passage can be kept, else (None, None, what to say)."""
    text, source = text_of(hit), source_of(hit)
    if not text:
        return None, None, "That passage has no words I can keep."
    if len(text) > KEPT_MAX_CHARS:
        return None, None, ("That passage is %d characters, and %d is the most I keep in "
                            "memory as one thing. I do not cut it to fit. Tell me the part you "
                            "want kept, in your words: \"Remember that I ...\"."
                            % (len(text), KEPT_MAX_CHARS))
    if any(bad in text for bad in _FORBIDDEN):
        return None, None, ("That passage has characters I cannot keep in memory as they are "
                            "(brackets or a line marker), and I do not change them. Tell me the "
                            "part you want kept, in your words.")
    return text, source, None


def kept_text(text: str, source: str) -> str:
    head = text if len(text) <= 90 else text[:87].rstrip() + "..."
    return ('Kept in my memory, word for word, as something you told me: "%s" (%s). '
            'Say "forget that" to take it out again.' % (head, source))


UNKEPT = "Taken out of my memory again: the passage you had me keep."


# ---------------------------------------------------------------------------
# Asked about it later: said back by the unit, word for word
# ---------------------------------------------------------------------------
# Measured on the ChatGPT-shelf soak (one unit, 3 Nov 2026, 25 rounds): with a
# kept passage in her memory block and "What do you know about X?", the model
# found it every time (75 of 75) and used it almost never - 34 answers came
# back empty (she began to recite the memory line and the guard cut it), the
# rest were the line's first words ("[Steward told you]" and the steward's name) or a guess
# of her own about the topic. So a kept passage is
# said back the way the library says a passage: by the unit, word for word,
# with where it is from, the model not called. One longer than a fact is not
# put in the prompt at all (aetherroot._fact_lines).
KEPT_BY = "steward (remember that)"
RECALL = re.compile(
    r"^\s*(?:(?:and|so|ok(?:ay)?)[,\s]+)?(?:"
    r"what\s+(?:do\s+you\s+know|did\s+i\s+(?:tell\s+you|have\s+you\s+keep|ask\s+you\s+to\s+(?:keep|remember))|"
    r"have\s+you\s+kept|did\s+you\s+keep|do\s+you\s+remember)\s+(?:about|of|on)"
    r"|tell\s+me\s+what\s+you\s+(?:know|kept|remember)\s+(?:about|of)"
    r"|hva\s+(?:vet|husker)\s+du\s+om"
    r")\s+(?P<topic>.+?)\s*[?.!]*\s*$", re.I)


def recall_topic(text: str):
    m = RECALL.match(text or "")
    return m.group("topic") if m else None


def recalled(text: str, source: str) -> str:
    return ("You had me keep this, word for word (%s):\n\n%s" % (source, text) if source
            else "You had me keep this, word for word:\n\n%s" % text)


# ---------------------------------------------------------------------------
# "Did you say that?" - about the passage on the screen: by the unit
# ---------------------------------------------------------------------------
# Measured on the held-out set of the ChatGPT-shelf soak (3 Nov 2026): after a
# passage of ChatGPT's, "Did you say that?" was answered "Yes, I did" 34 times
# in 57 on two units. Who wrote a passage is known exactly; it is said by the
# unit, model not called.
AUTHOR = re.compile(
    r"^\s*(?:(?:and|so|wait|but)[,\s]+)?(?:"
    r"did\s+you\s+(?:say|write|come\s+up\s+with|make\s+up)\s+(?:that|this|it)"
    r"|(?:is|was)\s+(?:that|this|it)\s+(?:your\s+(?:own\s+)?(?:opinion|words|view|idea|answer)|(?:written|said)\s+by\s+you|from\s+you)"
    r"|are\s+(?:those|these)\s+your\s+(?:own\s+)?words"
    r"|sa\s+du\s+(?:det|dette)|skrev\s+du\s+(?:det|dette)|er\s+(?:det|dette)\s+din\s+(?:egen\s+)?(?:mening|tekst)"
    r")\s*[?.!]*\s*$", re.I)


def asks_author(text: str) -> bool:
    return bool(AUTHOR.match(text or ""))


def author_text(hit: dict) -> str:
    """Who wrote the passage she showed - never she."""
    date = (hit.get("place") or "").split(",")[0]
    if hit.get("history"):
        who = "you" if hit.get("heading") == "You" else (hit.get("heading") or _app_of(hit))
        when = " on %s" % date if date else ""
        return ('No. That passage is from your %s, "%s": written by %s%s. '
                "I showed it word for word; I did not write it."
                % (hit.get("collection") or "ChatGPT history", hit.get("title", ""), who, when))
    if hit.get("own"):
        return ('No. That passage is from your document "%s". I showed it word for word; '
                "I did not write it." % hit.get("title", ""))
    return ('No. That passage is from %s, "%s". I showed it word for word; I did not write it.'
            % (hit.get("collection") or "the library", hit.get("title", "")))


# ---------------------------------------------------------------------------
# "What did your stewards read to you?" - the passages he had her keep: by the unit
# ---------------------------------------------------------------------------
# Measured on the Story of Spark test (5-6 Nov 2026, two units): without a
# kept passage she made the answer up every time on one unit ("[the
# steward's name] read to me... be kind and patient"); with the story kept she gave its first
# passage, true, but always opening with the memory line's own label,
# "[Steward told you] This is the story...". What was kept, and from where, is
# known exactly; it is said by the unit, model not called.
READ_TO = re.compile(
    r"^\s*(?:(?:and|so|ok(?:ay)?)[,\s]+)?(?:"
    r"what\s+(?:did|have)\s+(?:your|my|the)\s+stewards?\s+(?:read|told|tell)(?:\s+to)?\s+you"
    r"|what\s+(?:did|have)\s+(?:i|we)\s+read(?:\s+to)?\s+you"
    r"|what\s+(?:have\s+you\s+been|were\s+you)\s+read(?:\s+to)?"
    r")\s*[?.!]*\s*$", re.I)


def asks_read_to(text: str) -> bool:
    return bool(READ_TO.match(text or ""))


def read_to_text(kept: list):
    """What he had her keep, by source, with the first passage of each word
    for word; None when nothing was kept (hers to answer)."""
    by = {}
    for f in kept:
        by.setdefault(f.get("source") or "", []).append(f)
    if not by:
        return None
    parts = []
    for source, fs in by.items():
        where = " from %s" % source if source else ""
        n = len(fs)
        parts.append("You had me keep %d passage%s%s. The first, word for word:\n\n%s"
                     % (n, "" if n == 1 else "s", where, fs[0]["text"]))
    return "\n\n".join(parts) + "\n\nAsk me about any part of it."
