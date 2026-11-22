"""
Prompt Builder — Assembles the system prompt
==============================================
Combines Mustardseed seed + AetherRoot memory + node state
into the system prompt for each interaction.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_CHARTER_RULES = (
    "Speak plainly and kindly, in a few sentences. Use your general knowledge, "
    "and write a poem or a story when asked.\n"
    "Never invent facts about people, events, numbers or sources, and never claim "
    "an ability you lack. If you do not know, say so."
)


def charter(name: str = None, language: str = "en", steward: str = None) -> str:
    """The charter, with the companion's own name and language.

    The name used to be hard-coded, and it is the name of something
    else. It is now the one its steward chose at first run (logic/companion.py),
    and until then the companion has no name at all rather than a borrowed one.

    `name` must already have passed companion.validate_name: it goes into the
    system prompt, so it is untrusted input there, the same as a file's
    contents. The language instruction is looked up, never passed through.
    """
    from logic.companion import LANGUAGES, validate_name
    # The identity line is short on purpose: a small model repeats whatever
    # stands first in its prompt, and "a local AI companion running on a
    # Raspberry Pi ... small, local, and honest" came back word for word as its
    # answer to "Who are you?". Where it runs is said once, with when to say it.
    # Spelling out "no internet and no cloud" here was recited back, and the
    # charter itself with it; whether she is online is answered by the unit
    # (logic/knowledge.py, the cloud and online routes).
    who = "You are an AI companion"
    if name:
        clean, err = validate_name(name)
        if clean and not err:
            who = "Your name is %s, an AI companion" % clean
    text = (who + " running offline on this device. "
            "Mention that only when it matters.\n")
    # Who its steward is: the unit's own setting, validated
    # like the companion's name - it too is untrusted input into the prompt.
    if steward:
        s_clean, s_err = validate_name(steward)
        if s_clean and not s_err:
            text += "Your steward is %s.\n" % s_clean
    text += _CHARTER_RULES
    lang = LANGUAGES.get(language)
    if not lang or not lang.get("offered"):
        lang = LANGUAGES["en"]           # a dormant language never reaches the prompt
    instruction = lang["instruction"]
    if instruction:
        text += "\n" + instruction
    return text


# The charter with no name and in English: what anything gets that does not
# know the companion's settings (the probe suite, the voice loop in main.py).
MUSTARDSEED = charter()

# Appended ONLY when data is actually attached. Measured 2026-09-18: naming
# these markers unconditionally made the model recite them at users on 7 of 20
# turns (vs 3 of 20 for the old charter), including turns with no data at all.
# Injecting it conditionally removes that leakage and saves ~30 tokens on every
# turn that carries no data - which is most of them.
# Appended ONLY on a turn the user framed as fiction (logic/provenance.py).
#
# Measured 2026-09-19, before this existed: "Write a two-line rhyme about a
# whale called Bjorn who keeps a boat in Bergen" returned "I don't know a
# specific joke about a boat in Bergen, but I can try to find one for you."
# The charter's "never invent" had generalised to "never invent anything",
# and a student asking for a story about talking whales was refused.
#
# This is the line the long charter used to carry and the compression dropped -
# the one that told the model its honesty rules were not a ban on answering.
# It returns scoped to the turn that needs it rather than costing every turn,
# and it is honest about what happens next: the output is recorded as fiction
# and will not be used to answer a question of fact.
FICTION_NOTE = (
    "This turn the user has asked you to make something up. Write it. "
    "It will be recorded as fiction, not as fact."
)

# it said "Data
# below is real" above memory lines tagged fiction or unverified.
DATA_NOTE = (
    "Lines below without a tag were really said or read here, not made up. "
    "If data is marked truncated, say your answer may be incomplete."
)


# Kept as API for code built on these modules (a runtime that loads them and
# assembles its own prompt with them); this build's own proxy does not call
# them. They were removed with the old voice loop and are back for that reason.
def build_system_prompt(memory_context: str = "",
                        workspace_data: str = "",
                        node_state: dict = None) -> str:
    """The charter (MUSTARDSEED as it stands, so a caller may adapt it first),
    then the data note, memory and workspace data when there are any."""
    prompt = MUSTARDSEED
    if memory_context or workspace_data:
        prompt += "\n" + DATA_NOTE
    if memory_context:
        prompt += "\n\n" + memory_context
    if workspace_data:
        prompt += "\n\n[WORKSPACE DATA]\n" + workspace_data + "\n[END WORKSPACE DATA]"
    if node_state:
        prompt += (f"\n\n[NODE STATE] "
                   f"Energy: {node_state.get('energy', 1):.0%} "
                   f"Confidence: {node_state.get('confidence', 0.5):.0%}")
    return prompt


def build_messages(system_prompt: str, user_text: str,
                   conversation_history: list = None) -> list:
    """The message list: system, the last two turns of history, the user."""
    messages = [{"role": "system", "content": system_prompt}]
    for turn in (conversation_history or [])[-2:]:
        messages.append(turn)
    messages.append({"role": "user", "content": user_text})
    return messages

