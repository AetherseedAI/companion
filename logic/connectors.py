"""Connectors: what an errand may reach outside the companion (28 Nov 2026).

WHY. The operator, 28 Nov 2026: the Companion should be "more useful than
Meta's Muse agent", with four jobs: calendar and email, plans that run on,
home and family, and web errands. And: "if we need to make a Arc lite version
thats fine. I love companion". So the Companion grows the parts it needs, on
what it has (the approval queue, the chain, people, the Vault), instead of
being replaced. See logic/errands.py for the loop that uses these.

TIER 4. logic/levels.py reserves tier 4 for the network and keeps it off on
every unit. A connector is tier 4. It is not earned by trust points: the
owner switches each one on, one at a time, in the console, and can switch it
off again. That switch is the grant.

THREE KINDS OF TOOL.
- read: looks and changes nothing (a calendar, the inbox, a web page, a
  list). Runs at once, once the owner has switched the connector on.
- write: changes something at home, on the unit (a household list). Runs at
  once for a person at writer level or above; for anyone else it is filed in
  the approval queue.
- outward: goes out of the house or acts in someone's name (an email sent).
  Always filed in the approval queue, whoever asks, the owner included, and
  done by the unit only on a person's yes, exactly as filed.

NEVER. A connector never types a password or a card number into anything,
never pays, and never sees a turn marked Vault (errands do not run on them).
Its account passwords are typed by the owner at the unit's own screen or on
its own Wi-Fi, kept in a file only the companion's user can read (0600), and
never shown again, as the Claude key is.

THE NETWORK. The firewall (services/nftables.conf) lets the companion's own
user ask a name server and open HTTPS. Calendar (ICS) and web reads are HTTPS
and work through it. Email needs IMAP and SMTP (993, 465 or 587), which are
closed; opening them is the owner's step. Proton Mail Bridge on the unit
keeps email on 127.0.0.1 (IMAP 1143, SMTP 1025; docs/proton-bridge.md).

Standard library only: urllib, imaplib, smtplib, email, html.parser.
"""
import email
import email.policy
import imaplib
import ipaddress
import json
import os
import re
import smtplib
import socket
import ssl
import tempfile
import threading
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from html.parser import HTMLParser

READ, WRITE, OUTWARD = "read", "write", "outward"
WRITER_LEVELS = ("writer", "builder", "autonomous")
MAX_FETCH = 2 * 1048576
FETCH_TIMEOUT_S = 20
CONFIG_FILE = "connectors.json"
SECRETS_FILE = "connectors.secrets.json"


class ConnectorError(Exception):
    """A connector could not do what was asked; said as that, never as done."""


# ---- settings, kept beside the companion's other state ---------------------
class Settings:
    """connectors.json: which connector is on and its plain settings.
    connectors.secrets.json (0600): account passwords. Neither is ever sent."""

    def __init__(self, folder):
        self.folder = folder
        self._lock = threading.Lock()

    def _read(self, name):
        try:
            with open(os.path.join(self.folder, name), encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, name, value, mode=0o600):
        os.makedirs(self.folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.folder, prefix="." + name)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, indent=1)
            os.replace(tmp, os.path.join(self.folder, name))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def config(self, name):
        return dict(self._read(CONFIG_FILE).get(name) or {})

    def set_config(self, name, value):
        with self._lock:
            c = self._read(CONFIG_FILE)
            c[name] = value
            self._write(CONFIG_FILE, c, 0o600)

    def secret(self, name):
        v = self._read(SECRETS_FILE).get(name)
        return v if isinstance(v, str) else None

    def set_secret(self, name, value):
        with self._lock:
            s = self._read(SECRETS_FILE)
            if value:
                s[name] = value
            else:
                s.pop(name, None)
            self._write(SECRETS_FILE, s, 0o600)


# ---- the network, guarded --------------------------------------------------
def _public_host(host):
    """Every address the name resolves to is public: no loopback, private,
    link-local or reserved address, so a page cannot steer a read to the
    unit itself or the home network."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ConnectorError("the address could not be looked up")
    if not infos:
        raise ConnectorError("the address could not be looked up")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or \
                ip.is_multicast or ip.is_unspecified:
            raise ConnectorError("that address is inside a home or private network")
    return True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_https(url, opener=None, resolve=_public_host, max_bytes=MAX_FETCH):
    """GET an https:// address on a public host. Redirects are followed by
    hand, at most 3, each checked the same way. Returns (final url, bytes,
    content type)."""
    for _ in range(4):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" or not u.hostname or u.username or u.password:
            raise ConnectorError("only https:// addresses are read")
        resolve(u.hostname)
        req = urllib.request.Request(url, headers={"user-agent": "AetherSeed-Companion/1",
                                                   "accept": "text/html,text/plain,text/calendar,*/*;q=0.5"})
        open_ = opener or urllib.request.build_opener(
            _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())).open
        try:
            resp = open_(req, timeout=FETCH_TIMEOUT_S)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("location"):
                url = urllib.parse.urljoin(url, e.headers["location"])
                continue
            raise ConnectorError("the site answered %s" % e.code)
        except ConnectorError:
            raise
        except Exception as e:
            raise ConnectorError("the site could not be reached (%s)" % type(e).__name__)
        try:
            body = resp.read(max_bytes + 1)
            ctype = resp.headers.get("content-type", "") if getattr(resp, "headers", None) else ""
        finally:
            resp.close()
        if len(body) > max_bytes:
            raise ConnectorError("the page is larger than %d MB" % (max_bytes // 1048576))
        return url, body, ctype
    raise ConnectorError("too many redirects")


# ---- web: read a page --------------------------------------------------------
class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
             "article", "header", "footer", "table", "ul", "ol", "dd", "dt", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def page_text(body, ctype=""):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    text = body.decode(m.group(1) if m else "utf-8", errors="replace")
    if "html" not in (ctype or "").lower() and not re.search(r"<html|<body|<p[ >]", text[:2000], re.I):
        return "", re.sub(r"[ \t]+", " ", text).strip()
    p = _Text()
    p.feed(text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in "".join(p.parts).split("\n")]
    return " ".join(p.title.split()), "\n".join(ln for ln in lines if ln)


class Web:
    name = "web"
    title = "Web pages"
    MAX_TEXT = 12000

    def __init__(self, settings, fetch=fetch_https):
        self.settings, self.fetch = settings, fetch

    def tools(self):
        return [{"name": "web_read", "kind": READ,
                 "description": "Read the text of a public web page (https only). Returns the "
                                "page title and its text, cut at %d characters." % self.MAX_TEXT,
                 "input_schema": {"type": "object", "properties": {
                     "url": {"type": "string", "description": "An https:// address"}},
                     "required": ["url"]}}]

    def run(self, tool, args, ctx):
        url, body, ctype = self.fetch(str(args.get("url", "")))
        title, text = page_text(body, ctype)
        cut = len(text) > self.MAX_TEXT
        return {"url": url, "title": title, "text": text[:self.MAX_TEXT], "cut": cut}


# ---- calendar: read the provider's private address (ICS) -------------------
def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def _when(value, params):
    v = value.strip()
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", v):
        return datetime.strptime(v[:8], "%Y%m%d").date(), True
    if v.endswith("Z"):
        return datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
    # A local time with a TZID (or none) is kept as written: the unit says so.
    return datetime.strptime(v[:15], "%Y%m%dT%H%M%S"), False


def parse_ics(text):
    """The events of an iCalendar file: summary, start, end, location, all
    day, repeating. Repeats are not expanded: the first time is given, marked
    as repeating, rather than guessing at the rest."""
    events, cur = [], None
    for line in _unfold(text).splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None and "start" in cur:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            key, _, params = head.partition(";")
            key = key.upper()
            try:
                if key == "DTSTART":
                    cur["start"], cur["all_day"] = _when(value, params.upper())
                    cur["tz"] = (re.search(r"TZID=([^;:]+)", params) or [None, None])[1]
                elif key == "DTEND":
                    cur["end"], _ = _when(value, params.upper())
            except ValueError:
                cur["unreadable_time"] = True
            if key == "SUMMARY":
                cur["summary"] = value.replace("\\,", ",").replace("\\n", " ").strip()
            elif key == "LOCATION":
                cur["location"] = value.replace("\\,", ",").replace("\\n", " ").strip()
            elif key == "RRULE":
                cur["repeats"] = value.strip()
            elif key == "STATUS" and value.strip().upper() == "CANCELLED":
                cur["cancelled"] = True
    return events


def _as_dt(v):
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo is None else v.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.combine(v, datetime.min.time())


class Calendar:
    name = "calendar"
    title = "Calendar (private address)"
    MAX_EVENTS = 60

    def __init__(self, settings, fetch=fetch_https, today=None):
        self.settings, self.fetch = settings, fetch
        self.today = today or (lambda: datetime.now().date())

    def tools(self):
        return [{"name": "calendar_events", "kind": READ,
                 "description": "List the events in the owner's calendar between two dates "
                                "(inclusive). Times are as the calendar gives them; a repeating "
                                "event is listed at its first time and marked as repeating.",
                 "input_schema": {"type": "object", "properties": {
                     "from": {"type": "string", "description": "YYYY-MM-DD; default today"},
                     "to": {"type": "string", "description": "YYYY-MM-DD; default 7 days on"}}}}]

    def run(self, tool, args, ctx):
        urls = [u for u in (self.settings.config(self.name).get("urls") or []) if isinstance(u, str)]
        secret = self.settings.secret("calendar_url")
        if secret:
            urls = [secret] + urls
        if not urls:
            raise ConnectorError("no calendar address is set")
        try:
            d0 = date.fromisoformat(args.get("from") or self.today().isoformat())
            d1 = date.fromisoformat(args.get("to") or (d0 + timedelta(days=7)).isoformat())
        except ValueError:
            raise ConnectorError("dates are YYYY-MM-DD")
        lo, hi = datetime.combine(d0, datetime.min.time()), datetime.combine(d1, datetime.max.time())
        found, repeating = [], 0
        for url in urls[:4]:
            _, body, _ = self.fetch(url)
            for ev in parse_ics(body.decode("utf-8", errors="replace")):
                if ev.get("cancelled") or ev.get("unreadable_time"):
                    continue
                if ev.get("repeats"):
                    repeating += 1
                s = _as_dt(ev["start"])
                e = _as_dt(ev.get("end", ev["start"]))
                if (lo <= s <= hi) or (s < lo and e > lo):
                    found.append({"summary": ev.get("summary", "(no title)"),
                                  "start": ev["start"].isoformat(),
                                  "end": ev["end"].isoformat() if "end" in ev else None,
                                  "all_day": ev.get("all_day", False),
                                  "location": ev.get("location"),
                                  "time_zone": ev.get("tz"),
                                  "repeating": bool(ev.get("repeats"))})
        found.sort(key=lambda x: x["start"])
        return {"from": d0.isoformat(), "to": d1.isoformat(), "events": found[:self.MAX_EVENTS],
                "more": max(0, len(found) - self.MAX_EVENTS),
                "repeating_not_expanded": repeating}


# ---- email: IMAP to read, SMTP to send (always through the queue) ---------
def _plain(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return part.get_content()
        for part in msg.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                return page_text(part.get_content().encode("utf-8"), "text/html")[1]
        return ""
    if msg.get_content_type() == "text/html":
        return page_text(msg.get_content().encode("utf-8"), "text/html")[1]
    return msg.get_content() if msg.get_content_maintype() == "text" else ""


class Email:
    name = "email"
    title = "Email (IMAP and SMTP)"
    MAX_BODY = 8000
    MAX_LIST = 25

    def __init__(self, settings, imap=None, smtp=None):
        self.settings = settings
        self._imap = imap or self._imap_connect
        self._smtp = smtp or self._smtp_connect

    def _cfg(self):
        c = self.settings.config(self.name)
        pw = self.settings.secret("email_password")
        if not c.get("address") or not c.get("imap_host") or not pw:
            raise ConnectorError("the email account is not set up")
        return c, pw

    # Proton Mail Bridge, on the unit: IMAP 1143 and SMTP 1025 on 127.0.0.1,
    # STARTTLS with a certificate Bridge made for itself. The connection never
    # leaves the device, so its certificate is not checked; it is upgraded to
    # TLS whenever Bridge offers it, since Bridge may refuse a login without.
    @staticmethod
    def loopback(host):
        return host in ("127.0.0.1", "localhost", "::1")

    @staticmethod
    def _loopback_tls():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _imap_connect(self, c):
        host, port = c["imap_host"], int(c.get("imap_port") or 993)
        if self.loopback(host) and port != 993:
            m = imaplib.IMAP4(host, port, timeout=30)
            if "STARTTLS" in m.capabilities:
                m.starttls(ssl_context=self._loopback_tls())
            return m
        return imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=30)

    def _smtp_connect(self, c):
        host, port = c["smtp_host"], int(c.get("smtp_port") or 465)
        if port == 465:
            return smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
        s = smtplib.SMTP(host, port, timeout=30)
        if not self.loopback(host):
            s.starttls(context=ssl.create_default_context())
        else:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls(context=self._loopback_tls())
                s.ehlo()
        return s

    def tools(self):
        return [
            {"name": "email_search", "kind": READ,
             "description": "Search the owner's inbox. Returns sender, subject, date and an id "
                            "for each message, newest first (at most %d)." % self.MAX_LIST,
             "input_schema": {"type": "object", "properties": {
                 "text": {"type": "string", "description": "Words to look for; empty for the newest"},
                 "unread_only": {"type": "boolean"}}}},
            {"name": "email_read", "kind": READ,
             "description": "Read one message by its id from email_search.",
             "input_schema": {"type": "object", "properties": {"id": {"type": "string"}},
                              "required": ["id"]}},
            {"name": "email_send", "kind": OUTWARD,
             "description": "Send an email in the owner's name. It is NOT sent now: it is filed "
                            "for a person's approval and sent only on their yes, exactly as written.",
             "input_schema": {"type": "object", "properties": {
                 "to": {"type": "string", "description": "One address"},
                 "subject": {"type": "string"}, "body": {"type": "string"}},
                 "required": ["to", "subject", "body"]}},
        ]

    def run(self, tool, args, ctx):
        c, pw = self._cfg()
        if tool == "email_send":
            return self.send(args, c, pw)
        m = self._imap(c)
        try:
            m.login(c.get("user") or c["address"], pw)
            m.select("INBOX", readonly=True)
            if tool == "email_search":
                crit = ["UNSEEN"] if args.get("unread_only") else ["ALL"]
                text = " ".join(str(args.get("text") or "").split())[:100]
                if text:
                    crit += ["TEXT", '"%s"' % text.replace('"', "")]
                typ, data = m.uid("SEARCH", None, *crit)
                ids = (data[0] or b"").split()[-self.MAX_LIST:][::-1] if typ == "OK" else []
                out = []
                for uid in ids:
                    typ, d = m.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                    if typ == "OK" and d and isinstance(d[0], tuple):
                        h = email.message_from_bytes(d[0][1], policy=email.policy.default)
                        out.append({"id": uid.decode(), "from": str(h.get("from", "")),
                                    "subject": str(h.get("subject", "")), "date": str(h.get("date", ""))})
                return {"messages": out}
            uid = str(args.get("id", ""))
            if not uid.isdigit():
                raise ConnectorError("a message id is a number from email_search")
            typ, d = m.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not d or not isinstance(d[0], tuple):
                raise ConnectorError("no such message")
            msg = email.message_from_bytes(d[0][1], policy=email.policy.default)
            body = _plain(msg) or ""
            return {"id": uid, "from": str(msg.get("from", "")), "to": str(msg.get("to", "")),
                    "subject": str(msg.get("subject", "")), "date": str(msg.get("date", "")),
                    "text": body[:self.MAX_BODY], "cut": len(body) > self.MAX_BODY,
                    "attachments": [p.get_filename() for p in msg.walk() if p.get_filename()]}
        except (imaplib.IMAP4.error, OSError) as e:
            raise ConnectorError("the mail server refused or could not be reached (%s)" % type(e).__name__)
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def send(self, args, c, pw):
        """Only ever called by the approval queue, on a person's yes."""
        to = str(args.get("to", "")).strip()
        if not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", to):
            raise ConnectorError("one plain address is needed")
        if not c.get("smtp_host"):
            raise ConnectorError("no outgoing mail server is set")
        msg = EmailMessage()
        msg["From"], msg["To"] = c["address"], to
        msg["Subject"] = str(args.get("subject", ""))[:300]
        msg.set_content(str(args.get("body", "")))
        s = self._smtp(c)
        try:
            s.login(c.get("user") or c["address"], pw)
            s.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise ConnectorError("the mail was not sent (%s)" % type(e).__name__)
        finally:
            try:
                s.quit()
            except Exception:
                pass
        return {"sent": True, "to": to, "subject": msg["Subject"]}


# ---- home and family: shared lists ------------------------------------------
class Lists:
    """Lists the whole household shares (shopping, packing, chores), kept on
    the unit. Reading is open; a change runs at once for a person at writer
    level or above and is filed for anyone else."""
    name = "lists"
    title = "Household lists"
    MAX_LISTS, MAX_ITEMS, MAX_ITEM = 30, 200, 300
    NAME = re.compile(r"^[\w æøåÆØÅ-]{1,40}$")

    def __init__(self, settings, folder):
        self.settings, self.file = settings, os.path.join(folder, "household-lists.json")
        self._lock = threading.Lock()

    def tools(self):
        return [
            {"name": "list_read", "kind": READ,
             "description": "Read a household list, or the names of all lists when no name is given.",
             "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}}},
            {"name": "list_add", "kind": WRITE,
             "description": "Add items to a household list (made if new).",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
                 "required": ["name", "items"]}},
            {"name": "list_remove", "kind": WRITE,
             "description": "Remove items from a household list (done, bought, no longer needed).",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
                 "required": ["name", "items"]}},
        ]

    def _load(self):
        try:
            with open(self.file, encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data):
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.file), prefix=".lists")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.file)

    def _name(self, v):
        n = " ".join(str(v or "").split()).lower()
        if not self.NAME.match(n):
            raise ConnectorError("a list name is a few plain words")
        return n

    def run(self, tool, args, ctx):
        with self._lock:
            data = self._load()
            if tool == "list_read":
                if not args.get("name"):
                    return {"lists": {k: len(v.get("items", [])) for k, v in sorted(data.items())}}
                n = self._name(args["name"])
                if n not in data:
                    return {"name": n, "exists": False, "items": []}
                return {"name": n, "exists": True, "items": [i["text"] for i in data[n]["items"]]}
            n = self._name(args.get("name"))
            items = [" ".join(str(i).split())[:self.MAX_ITEM] for i in (args.get("items") or [])]
            items = [i for i in items if i][:50]
            if not items:
                raise ConnectorError("no items given")
            if tool == "list_add":
                if n not in data and len(data) >= self.MAX_LISTS:
                    raise ConnectorError("there are %d lists already" % self.MAX_LISTS)
                lst = data.setdefault(n, {"items": []})["items"]
                have, added = {i["text"].lower() for i in lst}, []
                for i in items:
                    if i.lower() not in have and len(lst) + len(added) < self.MAX_ITEMS:
                        added.append(i)
                        have.add(i.lower())
                lst.extend({"text": i, "by": ctx.get("speaker") or "", "at": ctx.get("now", "")} for i in added)
                self._save(data)
                return {"name": n, "added": added, "already_there": [i for i in items if i not in added],
                        "count": len(lst)}
            if n not in data:
                return {"name": n, "removed": [], "not_found": items}
            gone = {i.lower() for i in items}
            before = data[n]["items"]
            data[n]["items"] = [i for i in before if i["text"].lower() not in gone]
            removed = [i["text"] for i in before if i["text"].lower() in gone]
            self._save(data)
            return {"name": n, "removed": removed,
                    "not_found": [i for i in items if i.lower() not in {r.lower() for r in removed}],
                    "count": len(data[n]["items"])}


def build(folder, **overrides):
    """The connectors of a unit, keyed by name. Tests hand in their own."""
    from logic.plans import Plans       # plans use the connectors' kinds; imported here, not at the top
    s = Settings(folder)
    return s, {c.name: c for c in (
        overrides.get("web") or Web(s),
        overrides.get("calendar") or Calendar(s),
        overrides.get("email") or Email(s),
        overrides.get("lists") or Lists(s, folder),
        overrides.get("plans") or Plans(s, folder),
    )}
