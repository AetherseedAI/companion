"""Working memory: the last exchange of this conversation goes with the next
turn.

the steward, after a unit's first days on Qwen3 (finding 2 of): she
asks for context instead of finding it. Measured: on a unit, 12 of 73 short
follow-ups within five minutes of the turn before were answered by asking what
he meant ("Do you disagree?" - "I don't have a context for what you're
disagreeing about"); on copies of a unit, "And what day is that happening?"
did not find "... on Saturday" said two turns earlier, at either memory budget.

Why: the console sends each turn ALONE, and the only way a past turn reached
her was AetherRoot's long-term retrieval, which ranks by rare words in common.
A follow-up shares none with what it refers to. Every agent of the market map
read sends the recent turns of the conversation as real
user/assistant messages - OpenClaw, Hermes Agent, nanobot, NanoClaw, ZeroClaw,
PicoClaw, Moltis - and only then adds long-term memory. This is that, at the
size of this unit:

  - at most MAX_EXCHANGES (3) exchanges, each within WINDOW_S of the next turn;
  - the same speaker only: the steward's conversation is not shown to a guest -
    and, since, the same conversation: every guest is "Guest",
    so the console names each phone's conversation and the key is both
    (proxy._conversation_key). Conversations on two screens run side by side:
    a turn on one does not end the other;
  - kept in RAM, never on the card: in this process, and - when the unit
    gives it a folder in /run (AETHERSEED_SESSION_DIR; /run is RAM) - a copy
    there, so that a restart of the proxy (a model switch, an install) does
    not end the conversation. A reboot does. The long-term memory is where a
    turn is remembered;
  - the session, longer than what goes into a prompt: the last SESSION_KEEP
    exchanges within SESSION_WINDOW_S, for the console to draw again after a
    page is refreshed (the steward, 13 Nov: "When a page is refreshed the
    continuity feels lost"; what mattered was seeing his own wording again);
  - timed by time.monotonic, so that a clock set back or forward cannot make an old exchange new;
  - the assistant's side as it was SHOWN, cut at REPLY_MAX characters.

What it is not: a summary, a compaction, or anything the model writes. The
budget guard (logic/token_budget.enforce_budget) drops these before anything
else when a prompt does not fit, oldest first, a question and its answer
together.
"""
import json
import os
import threading
import time

WINDOW_S = 600           # ten minutes between the last exchange and this turn
# Three, not two. Tried on copies of a unit, the
# four turns of 77d: with two, "And what day is that happening?" lost "...on
# Saturday" behind an unrelated turn in between (a library passage), and she
# answered "the 10th day". With three, the turn it refers to is in front of
# her. Three exchanges cost about 150-450 tokens of a 1536-token prompt, and
# the budget guard drops the oldest first.
MAX_EXCHANGES = 3
# A prompt with room for more takes more: with the 4B's 2048-token ceiling,
# six (logic/token_budget; the budget guard still drops the oldest first).
MAX_EXCHANGES_ROOMY = 6
ROOMY_CEILING = 2048
# What the console draws again after a refresh: up to this many exchanges, as
# long as no gap between them is longer than the window.
SESSION_KEEP = 40
SESSION_WINDOW_S = 2 * 3600
SESSION_FILE = "session.json"
REPLY_MAX = 400          # characters of a reply carried (a passage can be long)
SHOWN_MAX = 4000         # characters of a reply kept for the console to draw again
USER_MAX = 400


def max_exchanges_for(ceiling) -> int:
    """How many recent exchanges go into a prompt for a model of this ceiling."""
    try:
        return MAX_EXCHANGES_ROOMY if int(ceiling) >= ROOMY_CEILING else MAX_EXCHANGES
    except (TypeError, ValueError):
        return MAX_EXCHANGES


class WorkingMemory:
    def __init__(self, window_s: float = WINDOW_S, max_exchanges: int = MAX_EXCHANGES,
                 clock=time.monotonic, folder=None, wall=time.time):
        self.window_s = window_s
        self.max_exchanges = max_exchanges
        self.clock = clock
        self.wall = wall
        self._lock = threading.Lock()
        self._turns = []             # (at, speaker, user, reply, when), oldest first
        self._shown = {}             # id(turn) -> the reply as shown, for the session
        self._said = {}              # id(turn) -> the words as typed, for the session
        self.path = os.path.join(folder, SESSION_FILE) if folder else None
        self._load()

    # ---- the copy in /run -------------------------------------------------
    def _load(self):
        """The session as the last process left it. CLOCK_MONOTONIC runs from
        boot, so its times stay comparable across a restart of the proxy; a
        reboot empties /run anyway. Anything unreadable is passed over."""
        if not self.path:
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                rows = json.load(f)
        except (OSError, ValueError):
            return
        now = self.clock()
        for r in rows if isinstance(rows, list) else []:
            try:
                at, who, user, reply = float(r["at"]), str(r["speaker"]), str(r["user"]), str(r["reply"])
                when = float(r.get("when") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if at > now:                 # not of this boot
                continue
            t = (at, who, user[:USER_MAX + 4], reply[:REPLY_MAX + 4], when)
            self._turns.append(t)
            self._shown[id(t)] = str(r.get("shown") or reply)[:SHOWN_MAX]
            self._said[id(t)] = str(r.get("said") or user)[:SHOWN_MAX]
        del self._turns[:-SESSION_KEEP * 2]

    def _save(self):
        """Written whole, under the lock, to a temporary name and moved into
        place: a reader never sees half a file."""
        if not self.path:
            return
        rows = [{"at": t[0], "speaker": t[1], "user": t[2], "reply": t[3], "when": t[4],
                 "shown": self._shown.get(id(t), t[3]), "said": self._said.get(id(t), t[2])}
                for t in self._turns]
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError:
            pass                         # RAM-only then: the process copy still holds it

    def add(self, speaker: str, user: str, reply: str):
        """One exchange as it happened: what was said, what was shown."""
        said = (user or "").strip()
        user = " ".join(said.split())
        shown = (reply or "").strip()
        reply = shown
        if not user or not reply:
            return
        if len(user) > USER_MAX:
            user = user[:USER_MAX].rsplit(" ", 1)[0] + " ..."
        if len(reply) > REPLY_MAX:
            reply = reply[:REPLY_MAX].rsplit(" ", 1)[0] + " ..."
        with self._lock:
            t = (self.clock(), speaker, user, reply, self.wall())
            self._turns.append(t)
            self._shown[id(t)] = shown[:SHOWN_MAX]
            self._said[id(t)] = said[:SHOWN_MAX]
            # room for a few conversations side by side, and the session
            gone = self._turns[:-max(self.max_exchanges * 8, 16, SESSION_KEEP * 2)]
            del self._turns[:-max(self.max_exchanges * 8, 16, SESSION_KEEP * 2)]
            for g in gone:
                self._shown.pop(id(g), None)
                self._said.pop(id(g), None)
            self._save()

    def session(self, speaker=None) -> list:
        """What the console draws again after a refresh: [{user, reply, at}]
        oldest first - the last SESSION_KEEP exchanges (of `speaker`, or of
        anyone on this proxy, which is one person's) with no gap longer than
        SESSION_WINDOW_S between them and now. `at` is wall-clock seconds,
        for showing only."""
        now = self.clock()
        out = []
        with self._lock:
            edge = now
            for t in reversed(self._turns):
                at, who, user, reply, when = t
                if speaker is not None and who != speaker:
                    continue
                if edge - at > SESSION_WINDOW_S:
                    break
                said = self._said.get(id(t)) or user
                out.append({"user": said, "reply": self._shown.get(id(t), reply), "at": when})
                edge = at
                if len(out) >= SESSION_KEEP:
                    break
        out.reverse()
        return out

    def last_reply(self, speaker: str):
        """The last answer of `speaker`'s conversation as it was shown (up to
        SHOWN_MAX characters), or None - "save it" saves this
        (logic/file_tools.py)."""
        with self._lock:
            for t in reversed(self._turns):
                if t[1] == speaker:
                    return self._shown.get(id(t), t[3])
        return None

    def recent(self, speaker: str, limit=None, window_s=None, full=False) -> list:
        """[(user, reply), ...], oldest first: the last exchanges of `speaker`
        (a speaker, or a speaker's conversation) that run up to now without a
        gap longer than the window. Another conversation's turns in between
        are passed over: until they ended this one, which was
        right for one screen and wrong for a phone beside it.

        `limit` and `window_s` in place of this model's own, and `full` for
        the exchanges as they were said and shown rather than cut to what the
        chip's prompt has room for: a turn Claude answers (logic/cloud.LIMITS)."""
        now = self.clock()
        limit = limit or self.max_exchanges
        window_s = window_s or self.window_s
        out = []
        with self._lock:
            edge = now
            for t in reversed(self._turns):
                at, who, user, reply, _when = t
                if who != speaker:
                    continue
                if edge - at > window_s:
                    break
                if full:
                    user = " ".join(self._said.get(id(t), user).split())
                    reply = self._shown.get(id(t), reply)
                out.append((user, reply))
                edge = at
                if len(out) >= limit:
                    break
        out.reverse()
        return out

    def forget(self, matcher):
        """Drop every exchange whose words `matcher(user + " " + reply)` says
        hold what was told to be forgotten (logic/forget.py)."""
        with self._lock:
            self._turns = [t for t in self._turns
                           if not matcher(" ".join((t[2], t[3], self._shown.get(id(t), ""),
                                                    self._said.get(id(t), ""))))]
            self._prune()
            self._save()

    def forget_last(self, speaker):
        """Drop the last exchange of `speaker`."""
        with self._lock:
            for i in range(len(self._turns) - 1, -1, -1):
                if self._turns[i][1] == speaker:
                    del self._turns[i]
                    self._prune()
                    self._save()
                    return

    def _prune(self):
        """The words kept beside each exchange, only for exchanges still kept."""
        alive = {id(t) for t in self._turns}
        for d in (self._shown, self._said):
            for k in [k for k in d if k not in alive]:
                del d[k]

    def clear(self):
        with self._lock:
            self._turns.clear()
            self._shown.clear()
            self._said.clear()
            self._save()


def as_messages(exchanges) -> list:
    """The exchanges as the chat messages they were."""
    msgs = []
    for user, reply in exchanges:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": reply})
    return msgs
