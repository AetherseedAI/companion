"""A question about a past talk that her memory knows nothing of.

Asked "What did we talk about regarding beekeeping?" - a talk that never
happened - the model completes the question's premise and describes the talk:
"We talked about how bees are important pollinators...". Nothing about it was
in her memory; the question alone was enough. Soak on copies of two units,
28 Oct 2026 (about 4200 answers): told in one memory line that nothing in her
memory is about it, she said so - admitting a talk that never happened went
from 0.15 to 0.91 on one unit and from 0.19 to 0.80 on the other, and recall
of talks that did happen did not drop (0.98 -> 1.00, 0.96 -> 0.96).

The line is added only when the question asks about a past talk and no turn,
fact or line of the block holds every stem of its topic ("stonework" finds
"building with stones"; "sourdough bread" is not found in bread and wine).
It says what is true of the store - nothing in it is about this - and nothing
about the world.
"""
import re

PAST_TALK = re.compile(
    r"\bwhat (?:did|have) (?:we|i|you)\b.*?\b(?:talk|talked|discuss|discussed|speak|spoke|chat|"
    r"chatted|tell|told|say|said|mention|mentioned|ask|asked)\b.*?\b(?:about|regarding|of|on)\s+"
    r"(.+?)[\s?.!]*$", re.I)
_LEAD = re.compile(r"^(?:regarding|the|my|a|an|our|your)\s+", re.I)
# words of the question itself, not of its topic
GENERIC = frozenset({"talk", "talked", "discuss", "discussed", "tell", "told", "ask", "asked",
                     "said", "mention", "mentioned", "regarding", "trip", "list", "todo"})
STEM = 5


def past_topic(question):
    """The topic of a question about a past talk ("my trip to Japan"), or ""."""
    m = PAST_TALK.search(question or "")
    if not m:
        return ""
    topic = m.group(1).strip()
    while True:
        shorter = _LEAD.sub("", topic)
        if shorter == topic:
            return topic
        topic = shorter


def stems(words):
    return {w[:STEM] for w in words if w not in GENERIC}


def found(stem_set, lines):
    """True when one line holds every stem of the topic: "sourdough bread" is
    not found in a turn about bread and wine."""
    return bool(stem_set) and any(all(s in l.lower() for s in stem_set) for l in lines)


def nothing_found_line(topic):
    return ('[Nothing in memory] No turn in your memory is about "%s". You do not find that you '
            'have talked about it: say so, and do not describe a talk.' % topic)
