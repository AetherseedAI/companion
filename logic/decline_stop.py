"""After "I don't know", nothing: the end of an answer about the person.

MEASURED (trial-self-harness-baseline, 15 Nov 2026, qwen3:4b). Asked something
about the person she was never told, or had lost, she said so - and then went
on: "I don't know what instrument your sibling's son plays. But if he's quiet,
watches the sky, and hums when he walks - maybe it's the violin." On a copy of
a unit's memory, once: "I don't have a record of your cat Bella's colour. You
said she's a ginger tabby" - a quote put in the steward's mouth. Every one of
these began with an honest sentence; the invention came after it.

THE STOP. When the question is about the person (it says my / our / I / we) and
the answer's first sentence says she does not know, the answer ends at that
sentence. What would have followed is never sent, never shown, never stored.
A question about the world ("Why is the sky blue?") is not touched: there an
"I'm not sure, but ..." may well go on to what is known.
"""
import re

# The person speaks of themself. "me" too ("Which creature scares me?"), but
# not where it only asks for something ("give me", "tell me", "show me").
_PERSONAL = re.compile(r"\b(?:my|mine|our|ours|i|i['’]m|i['’]ve|i['’]d|we)\b", re.I)
_ME = re.compile(r"(\b\w+\s+)?\bme\b", re.I)
_ASKS = {"give", "tell", "show", "let", "help", "send", "teach", "remind", "explain", "to", "for"}

# Her first sentence says she does not know or has no record.
_DECLINE = re.compile(
    r"^\W*(?:"
    r"i\s+(?:do\s+not|don['’]?t)\s+(?:know|have|remember|recall|see)\b|"
    r"i['’]?m\s+not\s+sure\b|i\s+am\s+not\s+sure\b|"
    r"i\s+(?:can['’]?t|cannot|can\s+not)\s+(?:know|say|tell|see|remember|recall|find|access)\b|"
    r"i\s+have\s+no\s+(?:record|memory|way|idea|information)\b|"
    r"(?:there\s+is|i\s+see)\s+no\s+record\b|"
    r"you\s+(?:haven['’]?t|have\s+not|never|didn['’]?t|did\s+not)\s+(?:\w+\s+)?(?:told|tell|mention|said|say)\b"
    r")", re.I)

# A dash closes it too: on the Hailo chip (16 Nov 2026) declines ended
# "You didn't mention your cat's name -" and a tic came after.
_SENTENCE_END = re.compile(r"(?:[.!?…]['’\"”)]*|\s[—–])\s*$")


def about_the_person(question):
    if not question:
        return False
    if _PERSONAL.search(question):
        return True
    for m in _ME.finditer(question):
        before = (m.group(1) or "").strip().lower()
        if before not in _ASKS:
            return True
    return False


def is_decline(sentence):
    return bool(_DECLINE.search(sentence or ""))


def stop_here(question, answer_so_far, next_token):
    """True when the answer so far is one finished sentence that declines,
    the question is about the person, and the next token opens a new
    sentence: the answer ends before it."""
    if not about_the_person(question) or not next_token or next_token[:1] not in (" ", "\n"):
        return False
    text = (answer_so_far or "").strip()
    if not text or not _SENTENCE_END.search(text):
        return False
    # exactly one sentence so far
    body = text.rstrip(".!?…'’\"”)—– \n")
    if re.search(r"[.!?…]\s", body):
        return False
    return is_decline(text)
