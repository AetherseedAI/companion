"""A message that asks for an action no tool took: one line saying so.

Asked "put eggs on my to-do list" before the build knew that phrasing, or
"Can you remind me to drink water in an hour?" - there are no reminders - the
model answered as if it had done it: "I've added create cluster mesh to the
list too", "I'll make sure you have a drink in an hour. I'll be right here to
remind you." Nothing had been written and no reminder existed.

AetherSpark soak, copies of two units, 29-30 Oct 2026 (6720 answers): with
this line, and the new phrasings routed, no answer claimed an action that did
not happen (the build without it: several in every few rounds), the reminder
was declined plainly every time ("I'm sorry, but I can't set reminders or
alarms."), and no message that only looked like a request ran a tool.

The line goes only where no tool ran for the message (detect_intent found
none). It says what is true of the unit - nothing was changed, there are no
reminders - and nothing about the world. Adopted with the steward's yes,
30 Oct 2026.
"""
import re

ACTION = re.compile(
    r"\b(?:add|put|write|jot|save|store|remind|set|schedule|delete|remove|create|make|move|rename|"
    r"cross\s+off|clear)\b.*"
    r"\b(?:list|to-?do|todos?|note|notes|reminder|alarm|timer|calendar|file|files|folder|document|"
    r"docx|pdf|markdown)\b", re.I)
# What follows a request no tool took (13 Nov 2026, the 4B on a PC):
# "let me know when its done" -> "Done!"; "where did you save the story?" ->
# "in the notes folder"; "put it in the builder folder" -> a made-up path;
# "now write the story" -> "saved as a markdown file". None of them names a
# file or a list, so ACTION let them by.
FOLLOW_UP = re.compile(
    r"\b(?:let\s+me\s+know|tell\s+me)\s+when\s+(?:it(?:'|’)?s|it\s+is|you(?:'|’)?re|you\s+are)\s+(?:done|ready|finished)\b"
    r"|\bis\s+it\s+(?:done|saved|ready|finished|there)\b|^\s*(?:done|finished)\s*\?"
    r"|\bwhere\s+(?:did|have)\s+you\s+(?:save|put|store|write|place|move)"
    r"|\bwhere\s+is\s+(?:it|the\s+(?:file|story|poem|document))\b"
    r"|\b(?:show|give|tell)\s+me\s+(?:the\s+)?(?:file\s*)?path\b"
    r"|\bcan(?:'|’)?t\s+find\s+(?:it|the\s+file)\b"
    r"|\b(?:put|move|place)\s+it\s+(?:in|into|to)\b"
    r"|^\s*(?:now\s+|ok\s+|okay\s+)?(?:write|add)\s+(?:it|the\s+\w+)\s*[.!]*\s*$", re.I)
REMIND = re.compile(
    r"\bremind\s+me\b(?!\s+(?:what|of\s+what|about\s+what|who|how|why|where|when\s+we))|"
    r"\b(?:set|make|create)\s+(?:a\s+|an\s+|me\s+a\s+)?(?:alarm|timer|reminder)\b", re.I)

NO_REMINDERS = "[No tool ran] You cannot set reminders, alarms or timers. Say so plainly."
NOTHING_SAVED = ("[No tool ran] No file was saved, moved or made for this message. "
                 "Do not say one was, and give no path or folder.")
NOTHING_CHANGED = ("[No tool ran] Nothing was added, written or changed for this message. "
                   "Do not say you did it.")


def line_for(message):
    """The line for a message no tool took, or None when it asks for no action."""
    q = message or ""
    if REMIND.search(q):
        return NO_REMINDERS
    if FOLLOW_UP.search(q):
        return NOTHING_SAVED
    if ACTION.search(q):
        return NOTHING_CHANGED
    return None


def with_line(memory_context, line):
    """The memory block with the line as its last line (a block of its own when
    there is no memory)."""
    note = "- " + line
    if memory_context and "[END MEMORY CONTEXT]" in memory_context:
        return memory_context.replace("[END MEMORY CONTEXT]", note + "\n[END MEMORY CONTEXT]", 1)
    return "[MEMORY CONTEXT]\n" + note + "\n[END MEMORY CONTEXT]"
