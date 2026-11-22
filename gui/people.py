"""More than one person on a unit, each with a root of their own.

A unit has one OWNER - the steward named at first start, whose root is the
unit's own (/var/lib/aetherseed) and whose passkey is the steward key - and
may have MEMBERS: people the owner added by name (tools/people.py, as root).

ONE ROOT, ONE PROCESS. A member's root is a directory of its own
(/var/lib/aetherseed-people/<id>) served by a proxy of its own
(aetherseed-proxy@<id>.service, a port of its own on loopback). Nothing is
shared between roots but what is the unit's: the companion's name, the
build's curriculum, the library, the model. A member's memory, facts, rings,
shelf, notes, record and trust standing are files in that member's root; no
query can cross, because no process holds two roots. The console (serve.py)
sends each signed-in person's requests to that person's proxy and to no other.

THE FIRST SIGN-IN SETS THE PASSKEY. The owner adds a name; whoever first signs
in under it chooses the passkey, and it is theirs from then on. Until then
the name can be claimed by anyone who can reach the console - the owner's
choice for a home network, said on the page - and
the owner can take a passkey away again (tools/people.py reset). The key file
is created exclusively: of two claims at once, one wins and the other is told
the name is taken. Only the hash is kept (gui/signin.py's record).

What this file does not do: it never reads or writes a root, and it is not a
second sign-in scheme - the lockout, the sessions and the passkey record are
gui/signin.py's.
"""
import json
import os
import re
import unicodedata

try:                                   # the console runs from gui/ (serve.py: `import signin`)
    import signin
except ImportError:                    # tools and tests import the package
    from gui import signin

PEOPLE_FILE = os.environ.get("AETHERSEED_PEOPLE", "/etc/aetherseed/people.json")
KEYS_DIR = os.environ.get("AETHERSEED_PEOPLE_KEYS", "/var/lib/aetherseed-keys")
ROOTS_DIR = os.environ.get("AETHERSEED_PEOPLE_ROOTS", "/var/lib/aetherseed-people")
FIRST_PORT = 8011
MAX_PEOPLE = 8
NAME_MAX = 24
_ID = re.compile(r"^[a-z][a-z0-9]{0,15}$")
# what a turn can already be stored as, or what the prompt gives meaning to
RESERVED = ("guest", "steward", "user", "ai", "trainer", "owner", "claude")


def valid_id(pid) -> bool:
    return isinstance(pid, str) and bool(_ID.match(pid))


def make_id(name: str, taken) -> str:
    """A short plain id for a name: its ASCII letters and digits, lower case
    ("Åse-Marie" -> "asemarie"); "p" when nothing is left; a number added
    while it is taken."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]", "", plain.lower())[:12]
    if not base or not base[0].isalpha():
        base = ("p" + base)[:12]
    pid, n = base, 2
    taken = set(taken) | {signin.OWNER}
    while pid in taken:
        pid, n = "%s%d" % (base, n), n + 1
    return pid


def _person_ok(p) -> bool:
    return (isinstance(p, dict) and valid_id(p.get("id"))
            and isinstance(p.get("name"), str) and 0 < len(p["name"]) <= NAME_MAX
            and isinstance(p.get("port"), int) and not isinstance(p["port"], bool)
            and 1024 < p["port"] < 65536)


def load(path: str = None) -> list:
    """The members, as the owner added them. A missing or unreadable file, or
    one that is not this shape, is no members: the unit is then what it was
    before - one steward."""
    try:
        with open(path or PEOPLE_FILE, "rb") as f:
            raw = f.read(65537)
        data = json.loads(raw.decode("utf-8")) if len(raw) <= 65536 else None
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    people = data.get("people") if isinstance(data, dict) else None
    if not isinstance(people, list):
        return []
    out, ids, names, ports = [], set(), set(), set()
    for p in people[:MAX_PEOPLE]:
        if not _person_ok(p):
            continue
        folded = signin.fold_name(p["name"])
        if p["id"] in ids or folded in names or p["port"] in ports:
            continue
        ids.add(p["id"]); names.add(folded); ports.add(p["port"])
        out.append({"id": p["id"], "name": p["name"], "port": p["port"]})
    return out


def find(people: list, typed_name):
    """The member a typed name means, or None."""
    for p in people:
        if signin.names_match(typed_name, p["name"]):
            return p
    return None


def by_id(people: list, pid):
    for p in people:
        if p["id"] == pid:
            return p
    return None


def backend(person: dict) -> str:
    return "http://127.0.0.1:%d" % person["port"]


def root_dir(pid: str, roots_dir: str = None) -> str:
    if not valid_id(pid):
        raise ValueError("not a person's id")
    return os.path.join(roots_dir or ROOTS_DIR, pid)


def key_path(pid: str, keys_dir: str = None) -> str:
    if not valid_id(pid):
        raise ValueError("not a person's id")
    return os.path.join(keys_dir or KEYS_DIR, pid + ".key")


def has_key(pid: str, keys_dir: str = None) -> bool:
    """Has this name been claimed? A key file that is not a record counts as
    claimed: it is the owner's to reset, never a second first time."""
    return os.path.lexists(key_path(pid, keys_dir))


def claim(pid: str, passkey, keys_dir: str = None) -> str:
    """Set a member's passkey for the first time. Returns "claimed", "taken"
    (somebody set one already) or "bad_passkey". The file is created
    exclusively, so two claims cannot both win."""
    if not signin.passkey_shape_ok(passkey):
        return "bad_passkey"
    path = key_path(pid, keys_dir)
    rec = signin.make_record(passkey, "own")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return "taken"
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rec, f)
        f.flush()
        os.fsync(f.fileno())
    return "claimed"


def check(pid: str, passkey, keys_dir: str = None) -> bool:
    return signin.passkey_matches(signin.load_record(key_path(pid, keys_dir)), passkey)


def reset(pid: str, keys_dir: str = None) -> bool:
    """Take a member's passkey away, so the name's next sign-in sets a new one.
    The owner's to do (tools/people.py, as root)."""
    try:
        os.unlink(key_path(pid, keys_dir))
        return True
    except FileNotFoundError:
        return False


def name_error(name, people: list, owner_name: str = None, companion_name: str = None):
    """Why this name cannot be added, or None. The rules of a companion's
    name (it is put before what the person says, in the prompt), and not a
    name that already means somebody."""
    try:
        from logic import companion
    except ImportError:
        return "unavailable"
    clean, err = companion.validate_name(name)
    if err:
        return err
    folded = signin.fold_name(clean)
    if folded in RESERVED:
        return "reserved"
    for other in (owner_name, companion_name):
        if other and signin.fold_name(other) == folded:
            return "in_use"
    if find(people, clean) is not None:
        return "in_use"
    if len(people) >= MAX_PEOPLE:
        return "full"
    return None


def add(people: list, name: str) -> dict:
    """A new member's entry (not written): an id and the first free port."""
    from logic import companion
    clean, _ = companion.validate_name(name)
    ports = {p["port"] for p in people}
    port = FIRST_PORT
    while port in ports:
        port += 1
    return {"id": make_id(clean, {p["id"] for p in people}), "name": clean, "port": port}


def save(people: list, path: str = None):
    path = path or PEOPLE_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"people": people}, f, indent=1, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def public(people: list, keys_dir: str = None) -> list:
    """What the sign-in page may show before anyone has signed in: the names,
    and which of them nobody has claimed yet. No ids, no ports."""
    return [{"name": p["name"], "first_time": not has_key(p["id"], keys_dir)} for p in people]
