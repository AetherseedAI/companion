"""Plans that run on: a goal the Companion keeps working on, and reports back (28 Nov 2026).

WHY. One of the four jobs the operator set on 28 Nov 2026, from Meta's Muse:
"turns long-term goals into personalized plans ... and advances the work on
its own." Here a plan is a standing errand (logic/errands.py): a goal, how
often to look at it, and who it is for. When it is due, the unit runs it as
an errand in that person's name, with what the last run found, and keeps the
report for them. Reads run; anything outward is filed for a yes, as always.

STARTED ONLY ON A YES. A plan acts on its own later, so making one is itself
outward: Claude can propose a plan (plan_create), but it is filed in the
approval queue and starts only when a person approves it. The owner can pause
or remove any plan in the console.

LIMITS. At most MAX_PLANS plans; none more often than every MIN_HOURS hours;
each run counts against the day's errands like any other. A plan that fails
three times in a row pauses itself and says why.

WHAT IT IS NOT. A plan never runs while Claude is off, never on a Vault
matter, and never writes into anyone's memory: its reports are kept here, in
plans.json, and shown in the console.
"""
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from logic.connectors import READ, OUTWARD, ConnectorError

PLANS_FILE = "plans.json"
MAX_PLANS = 12
MIN_HOURS = 6
MAX_HOURS = 24 * 14
MAX_GOAL = 600
FAILS_TO_PAUSE = 3


def _iso(t):
    return t.isoformat(timespec="seconds")


class Plans:
    """The plans of a unit, and the connector Claude uses to propose one."""
    name = "plans"
    title = "Plans that run on"

    def __init__(self, settings, folder, clock=None):
        self.settings = settings
        self.file = os.path.join(folder, PLANS_FILE)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    # ---- storage ---------------------------------------------------------------
    def _load(self):
        try:
            with open(self.file, encoding="utf-8") as f:
                v = json.load(f)
            if isinstance(v, dict) and isinstance(v.get("plans"), list):
                return v
        except (OSError, ValueError):
            pass
        return {"next_id": 1, "plans": []}

    def _save(self, data):
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.file), prefix=".plans")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.file)

    def all(self):
        with self._lock:
            return self._load()["plans"]

    # ---- the connector: what Claude may call ------------------------------
    def tools(self):
        return [
            {"name": "plan_list", "kind": READ,
             "description": "List the household's standing plans: goal, how often, for whom, the last report.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "plan_create", "kind": OUTWARD,
             "description": "Propose a standing plan: a goal you will look at again every so many hours, "
                            "reporting what changed. It does NOT start now: it is filed for a person's yes, "
                            "because it will act later on its own. Reads run when it is due; anything that "
                            "goes out still waits for a yes each time.",
             "input_schema": {"type": "object", "properties": {
                 "goal": {"type": "string", "description": "What to keep working on, in the person's words"},
                 "every_hours": {"type": "integer", "description": "How often (%d to %d hours)" % (MIN_HOURS, MAX_HOURS)}},
                 "required": ["goal", "every_hours"]}},
        ]

    def run(self, tool, args, ctx):
        if tool == "plan_list":
            return {"plans": [self._public(p) for p in self.all()]}
        if tool == "plan_create":       # only ever reached through the approval queue
            return self.create(args.get("goal"), args.get("every_hours"), ctx.get("speaker") or "")
        raise ConnectorError("no such plan tool")

    @staticmethod
    def _public(p):
        return {k: p.get(k) for k in ("id", "goal", "every_hours", "for", "status", "next_at", "last_at",
                                      "last_report", "runs", "paused_because")}

    # ---- the owner's and the queue's actions -------------------------------
    def create(self, goal, every_hours, for_whom):
        goal = " ".join(str(goal or "").split())
        if not goal or len(goal) > MAX_GOAL:
            raise ConnectorError("a plan's goal is a sentence or two")
        try:
            hours = int(every_hours)
        except (TypeError, ValueError):
            raise ConnectorError("how often is a number of hours")
        if not MIN_HOURS <= hours <= MAX_HOURS:
            raise ConnectorError("a plan runs every %d to %d hours" % (MIN_HOURS, MAX_HOURS))
        with self._lock:
            data = self._load()
            if sum(1 for p in data["plans"] if p["status"] != "removed") >= MAX_PLANS:
                raise ConnectorError("there are %d plans already" % MAX_PLANS)
            now = self.clock()
            p = {"id": data["next_id"], "goal": goal, "every_hours": hours, "for": for_whom,
                 "status": "active", "created_at": _iso(now), "next_at": _iso(now),
                 "last_at": None, "last_report": None, "runs": 0, "fails": 0}
            data["next_id"] += 1
            data["plans"].append(p)
            self._save(data)
            return {"created": True, "plan": self._public(p)}

    def set_status(self, pid, status):
        if status not in ("active", "paused", "removed"):
            raise ConnectorError("bad status")
        with self._lock:
            data = self._load()
            p = next((x for x in data["plans"] if x["id"] == pid), None)
            if p is None or p["status"] == "removed":
                raise ConnectorError("no such plan")
            p["status"] = status
            if status == "active":
                p["fails"], p["paused_because"] = 0, None
                p["next_at"] = _iso(self.clock())
            self._save(data)
            return self._public(p)

    # ---- running what is due ------------------------------------------------
    def due(self):
        now = self.clock()
        return [p for p in self.all() if p["status"] == "active"
                and datetime.fromisoformat(p["next_at"]) <= now]

    def record_run(self, pid, report=None, error=None):
        with self._lock:
            data = self._load()
            p = next((x for x in data["plans"] if x["id"] == pid), None)
            if p is None:
                return None
            now = self.clock()
            p["last_at"], p["runs"] = _iso(now), p.get("runs", 0) + 1
            p["next_at"] = _iso(now + timedelta(hours=p["every_hours"]))
            if error:
                p["fails"] = p.get("fails", 0) + 1
                p["last_report"] = {"failed": error}
                if p["fails"] >= FAILS_TO_PAUSE:
                    p["status"], p["paused_because"] = "paused", "failed %d times in a row: %s" % (p["fails"], error)
            else:
                p["fails"] = 0
                p["last_report"] = {k: report.get(k) for k in ("text", "done", "waiting", "failed")}
            self._save(data)
            return self._public(p)


PLAN_NOTE = ("This is a standing plan you agreed to keep working on for {who}. Goal: {goal}. "
             "Look at what is needed now and do what you can with your tools. {last} "
             "End with a short report for {who}: what changed since last time, what you did, "
             "and what is waiting for their yes.")


def run_due(errands, plans, level, system=""):
    """Run every due plan as an errand in its person's name. Returns the plans
    run, each with its report or the reason it did not run."""
    out = []
    if not errands.cloud.ready() or not errands.tools():
        return out          # Claude off or nothing switched on: wait, and count nothing against the plan
    for p in plans.due():
        last = ("Last time you reported: %s" % (p["last_report"] or {}).get("text", "")[:800]
                if p.get("last_report") and p["last_report"].get("text") else "This is the first run.")
        note = PLAN_NOTE.format(who=p["for"] or "the household", goal=p["goal"], last=last)
        try:
            report = errands.run(note, p["for"], level, system=system, plan=p["id"])
            out.append(plans.record_run(p["id"], report=report))
        except Exception as e:      # CloudError and anything else: said, counted, never silent
            out.append(plans.record_run(p["id"], error=str(e)[:200] or type(e).__name__))
    return out
