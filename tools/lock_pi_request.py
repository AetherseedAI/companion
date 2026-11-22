#!/usr/bin/env python3
"""Lock the image's "pi" account from the unit's own screen, once the admin's
password is shown to work (the operator, 15 Nov 2026: a button that sends the
command from the kiosk during onboarding). Run as root by
aetherseed-lock-pi.service when the console leaves a request.

    the request (/run/aetherseed-gui/lock-pi-request, mode 600): one line,
    the admin's password as typed.

THE CONFIRMATION. The admin is the account the first start made
(/etc/aetherseed/admin-account). Its password is checked the way a sign-in
checks it: `su <admin> -c true` started as an UNPRIVILEGED user (aetherseed)
in a pseudo-terminal, so PAM itself checks it, whatever hash the system
uses. Root's own su would not ask. Only if that sign-in succeeds - and the
admin is in the sudo group - is pi locked (tools/lock_default.sh's way:
locked and expired, files kept). Otherwise nothing changes.

The password is read from the request, which is removed at once, and written
only to su's terminal: never to a log, the journal or the result.
"""
import grp
import os
import pty
import pwd
import select
import subprocess
import sys
import tempfile
import time

REQUEST = os.environ.get("AETHERSEED_LOCK_PI_REQUEST", "/run/aetherseed-gui/lock-pi-request")
RESULT = os.environ.get("AETHERSEED_LOCK_PI_RESULT", "/run/aetherseed-gui/lock-pi-result")
RECORD = os.environ.get("AETHERSEED_ADMIN_RECORD", "/etc/aetherseed/admin-account")
OLD = os.environ.get("AETHERSEED_DEFAULT_ACCOUNT", "pi")
CHECK_AS = os.environ.get("AETHERSEED_CHECK_AS", "aetherseed")
LOCK = os.environ.get("AETHERSEED_LOCK_TOOL", "usermod")
# stand-ins for the tests: a command given the password on its input (exit 0 =
# it works), and the sudo group's members
SIGNIN_CHECK = os.environ.get("AETHERSEED_SIGNIN_CHECK")
SUDO_MEMBERS = os.environ.get("AETHERSEED_SUDO_MEMBERS")
PASSWD_STATUS = os.environ.get("AETHERSEED_PASSWD_STATUS")      # "L" or "P"


def finish(*lines):
    # Made in root's own folder (/run, the console folder's parent) and
    # renamed in: a rename replaces a link the console might have left, where
    # opening "<result>.tmp" in the console's folder would follow it.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.dirname(RESULT)),
                               prefix=".aetherseed-lock-pi-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, RESULT)
    sys.exit(0)


def sign_in_works(admin, password):
    """True if `su admin -c true`, started as CHECK_AS, accepts the password."""
    if SIGNIN_CHECK:
        return subprocess.run([SIGNIN_CHECK, admin], input=password + "\n", text=True,
                              capture_output=True).returncode == 0
    pid, fd = pty.fork()
    if pid == 0:
        try:
            u = pwd.getpwnam(CHECK_AS)
            os.setgroups([])
            os.setgid(u.pw_gid)
            os.setuid(u.pw_uid)
            os.environ.update(HOME="/", LANG="C", LC_ALL="C")
            os.execvp("su", ["su", admin, "-c", "true"])
        finally:
            os._exit(127)
    sent, buf, end = False, b"", time.time() + 20
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                chunk = os.read(fd, 1024)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if not sent and b"assword" in buf:
                os.write(fd, password.encode("utf-8") + b"\n")
                sent = True
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        return False
    try:
        _, status = os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    os.close(fd)
    return sent and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def main():
    try:
        fd = os.open(REQUEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)    # never through a link
        with os.fdopen(fd, encoding="utf-8") as f:
            password = f.readline(200).rstrip("\n")
    except OSError:
        finish("error", "no_request", "Nothing was asked.")
    finally:
        try:
            os.unlink(REQUEST)
        except OSError:
            pass
    try:
        admin = open(RECORD, encoding="utf-8").readline().strip()
    except OSError:
        admin = ""
    if not admin:
        finish("error", "no_admin", "This unit has no admin account from its first start.")
    if not SIGNIN_CHECK:
        try:
            pwd.getpwnam(admin)
        except KeyError:
            finish("error", "no_admin", "The admin account is not on this unit.")
    members = SUDO_MEMBERS.split(",") if SUDO_MEMBERS is not None else grp.getgrnam("sudo").gr_mem
    if admin not in members:
        finish("error", "not_sudo", "The admin account cannot use sudo, so pi stays as it is.")
    try:
        locked = (["pi", PASSWD_STATUS] if PASSWD_STATUS else
                  subprocess.run(["passwd", "-S", OLD], capture_output=True, text=True).stdout.split())
    except OSError:
        locked = []
    if len(locked) > 1 and locked[1] == "L":
        finish("ok", "already", OLD)
    if not sign_in_works(admin, password):
        del password
        finish("error", "wrong_password", "That is not the admin's password. pi stays as it is.")
    del password
    if subprocess.run([LOCK, "-L", "-e", "1", OLD], capture_output=True).returncode != 0:
        finish("error", "lock", "pi could not be locked.")
    print("[lock-pi] %s locked after the admin's sign-in was checked" % OLD, flush=True)
    finish("ok", "locked", OLD)


if __name__ == "__main__":
    main()
