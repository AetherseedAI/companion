#!/bin/bash
# The first start of a unit that is onboarded where it will live.
#
# "Onboarded on-site means the user will pick name passkey
# and start it for the first time." Until now a unit's own Wi-Fi was set up by
# whoever installed it, at a shell (tools/hotspot.sh on), and its clock by the
# network it was built on. A unit that is copied from a source card and opened
# in someone's home has neither a shell nor - sincea network
# that tells it the time, and the board has no battery on its clock.
#
# So the first-start screen asks for three things: the companion's name (as it
# always did), the date and time, and a passkey for the unit's own Wi-Fi. The
# name goes where it always went. The other two need root, and the console
# has none and must not get any (it runs unprivileged, NoNewPrivileges). It
# leaves a request in its own runtime directory, as it does for shutdown;
# services/aetherseed-first-start.path sees it and starts this, as root.
#
#   the request, six lines:  2026-10-07 15:30
#                            <the Wi-Fi passkey, as typed (empty for LAN only)>
#                            <the steward's own passkey, as typed>
#                            <the admin account's name>
#                            <the admin account's password, as typed>
#                            hidden | visible | lan   (the unit's own network)
#
# FROM A PHONE (21 Nov 2026, the operator: "she must be able to do it from her
# phone"): an armed unit shows the setup network "AetherSeed" (tools/hotspot.sh
# setup), the phone joins it and the console takes the first start from there.
# The unit's own network is set up LAST, after the answer is written: the phone
# is on the setup network and loses it the moment the unit switches.
#
# What this does with it, and nothing else:
#   - removes the request at once (tmpfs, mode 600, and now gone);
#   - refuses unless the unit is ARMED: /etc/aetherseed/first-start exists.
#     tools/source_card.sh puts it there when a card is made a source; this
#     removes it when the first start is done. A unit that was set up at a
#     shell never has it, and nothing here can change
#     their clock or their passkey;
#   - sets the clock, and saves it where the unit resumes from at start;
#   - sets up the unit's Wi-Fi, named after the companion, with the passkey -
#     through tools/hotspot.sh, which checks both and keeps the passkey in the
#     network profile and nowhere else;
#   - makes the unit's ADMIN ACCOUNT (15 Nov 2026, the operator: "an aetherseed admin
#     user on all devices that can do updates in the field, the name and pw
#     set by the user on first boot"): a login of the owner's choosing, in the
#     sudo group, with the password they typed - set through chpasswd on its
#     standard input, never on a command line, in a file or a log. A name that
#     is already an account on the unit is refused, so no existing account
#     (root, pi, the services' own) can be taken over this way;
#   - names the unit after the companion on the local network (hostname, and
#     avahi announces <name>.local: http://aria.local:2077);
#   - leaves its answer for the console to show: ok, or what went wrong.
#
# No passkey or password is ever written to a log, the journal or the result.
set -u
export PATH=$PATH:/usr/sbin:/sbin

RUN_DIR=${AETHERSEED_GUI_RUN:-/run/aetherseed-gui}
REQUEST=$RUN_DIR/first-start-request
RESULT=$RUN_DIR/first-start-result
FLAG=${AETHERSEED_FIRST_START_FLAG:-/etc/aetherseed/first-start}
HOTSPOT=${AETHERSEED_HOTSPOT:-/opt/aetherseed/tools/hotspot.sh}
STATUS_URL=${AETHERSEED_STATUS_URL:-http://127.0.0.1:8001/aetherseed/status}
SET_CLOCK=${AETHERSEED_SET_CLOCK:-}          # a stand-in for the tests
STEWARD_KEY=${AETHERSEED_STEWARD_KEY_TOOL:-/opt/aetherseed/tools/steward_key.py}
SAVED_CLOCK=${AETHERSEED_SAVED_CLOCK:-/var/lib/systemd/timesync/clock}
# stand-ins for the tests (each takes what the real one takes)
ADMIN_MADE=${AETHERSEED_ADMIN_MADE:-/etc/aetherseed/first-start-admin}   # the name this made, if a later step failed
ADD_ADMIN=${AETHERSEED_ADD_ADMIN:-}          # ADD_ADMIN NAME ; password on stdin
ADMIN_RECORD=${AETHERSEED_ADMIN_RECORD:-/etc/aetherseed/admin-account}   # who the admin is (tools/lock_default.sh)
SSHD_DROPIN=${AETHERSEED_SSHD_DROPIN:-/etc/ssh/sshd_config.d/50-aetherseed-admin.conf}
SET_HOSTNAME=${AETHERSEED_SET_HOSTNAME:-}    # SET_HOSTNAME NAME

# What the console is told: "ok" and the network's name; or "error", a word
# the console has its own sentence for in each language, and this one.
finish() {      # finish ok NAME | finish error CODE "one line"
  # Made in root's own folder (/run, the console folder's parent) and renamed
  # in: mv replaces a link the console might have left, where writing
  # "<result>.tmp" in the console's folder would follow it.
  local tmp
  tmp=$(mktemp -p "$(dirname "$RUN_DIR")" .aetherseed-first-start.XXXXXX) &&
    printf '%s\n' "$@" > "$tmp" && chmod 644 "$tmp" && mv -fT "$tmp" "$RESULT"
  echo "first-start: $*"
  # A refusal is an answer, not a failure of the unit: the console shows it,
  # and `systemctl --failed` stays a list of things that are broken.
  exit 0
}

# never through a link: the folder is the console's, the reader root
[ -L "$REQUEST" ] && { rm -f "$REQUEST"; echo "first-start: a link, not a request"; exit 0; }
[ -f "$REQUEST" ] && [ -r "$REQUEST" ] || { echo "first-start: no request"; exit 0; }
when=""; key=""; own=""; admin=""; apw=""; net=""
{ IFS= read -r when || true; IFS= read -r key || true; IFS= read -r own || true
  IFS= read -r admin || true; IFS= read -r apw || true; IFS= read -r net || true; } < "$REQUEST"
case $net in hidden|visible|lan) ;; "") net=hidden ;; *) net=bad ;; esac
rm -f "$REQUEST"
forget() { unset key own apw; }

[ -e "$FLAG" ] || { forget; finish error not_armed "This unit has been started before."; }
[ "$net" != bad ] || { forget; finish error bad_network "Choose how the unit's own Wi-Fi should be: hidden, visible, or none."; }
if [ "$net" = lan ] && ! "$HOTSPOT" can-lan >/dev/null 2>&1; then
  forget; finish error lan_unreachable "With no network cable and no home Wi-Fi, LAN only would leave the unit unreachable. Choose hidden or visible, or plug in a cable first."
fi

# The admin account, checked before anything is changed. A login name as
# Debian's adduser takes it, and not one the unit already has.
printf '%s' "$admin" | LC_ALL=C grep -Eq '^[a-z][a-z0-9_-]{1,30}$' \
  || { forget; finish error bad_admin_name "The admin name must be 2 to 31 small letters, digits, - or _, starting with a letter."; }
made=$(cat "$ADMIN_MADE" 2>/dev/null || true)
if [ -z "$ADD_ADMIN" ] && [ "$admin" != "$made" ] && getent passwd "$admin" >/dev/null 2>&1; then
  forget; finish error admin_taken "That name is already an account on this unit. Choose another."
fi
printf '%s' "$apw" | LC_ALL=C grep -Eq '^[ -~]{12,128}$' \
  || { forget; finish error bad_admin_password "The admin password must be 12 to 128 plain characters."; }
{ [ -z "$key" ] || [ "$apw" != "$key" ]; } && [ "$apw" != "$own" ] \
  || { forget; finish error same_admin_password "The admin password must not be either passkey."; }

# The steward's own passkey. The
# Wi-Fi passkey is held by everyone given the Wi-Fi and the steward's name is
# no secret, so a steward who signs in with the Wi-Fi passkey is a guest who
# was told it. Asked for before anything is changed.
# LC_ALL=C: in a UTF-8 locale the range [ -~] does not match plain ASCII on the units' grep
printf '%s' "$own" | LC_ALL=C grep -Eq '^[ -~]{8,63}$' \
  || { forget; finish error bad_steward_key "Your own passkey must be 8 to 63 plain characters."; }
[ "$net" = lan ] || [ "$own" != "$key" ] || { forget; finish error same_key "Your own passkey must not be the Wi-Fi passkey."; }
if [ "$net" != lan ]; then
  printf '%s' "$key" | LC_ALL=C grep -Eq '^[ -~]{8,63}$' \
    || { forget; finish error bad_passkey "The passkey must be 8 to 63 plain characters."; }
fi

# ---- the clock --------------------------------------------------------------
if ! printf '%s' "$when" | grep -Eq '^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01]) ([01][0-9]|2[0-3]):[0-5][0-9]$' \
   || ! date -d "$when" >/dev/null 2>&1; then
  forget; finish error bad_when "That is not a date and time I can set."
fi
if [ -n "$SET_CLOCK" ]; then
  $SET_CLOCK "$when" || { forget; finish error clock "The clock could not be set."; }
else
  date -s "$when:00" >/dev/null 2>&1 || { forget; finish error clock "The clock could not be set."; }
  # The board's own clock, for as long as it has power; and the stamp the
  # unit resumes from at its next start (it asks no network:).
  hwclock -w >/dev/null 2>&1 || true
  [ -e "$SAVED_CLOCK" ] && touch "$SAVED_CLOCK" 2>/dev/null || true
  systemctl try-restart systemd-timesyncd >/dev/null 2>&1 || true
fi

# ---- the unit's own Wi-Fi ---------------------------------------------------
# Named after the companion. A network name is plain characters only, and a
# companion may be called Bjørn: the name is written in plain letters for the
# network, and the console says what the network is called.
name=$(curl -s --max-time 5 "$STATUS_URL" 2>/dev/null | python3 -c '
import json, sys, unicodedata
try:
    c = json.load(sys.stdin).get("companion") or {}
    n = (c.get("name") or "") if c.get("configured") else ""
except Exception:
    n = ""
for a, b in (("æ", "ae"), ("Æ", "Ae"), ("ø", "o"), ("Ø", "O"), ("å", "a"), ("Å", "A"),
             ("ß", "ss"), ("ð", "d"), ("Ð", "D"), ("þ", "th"), ("Þ", "Th")):
    n = n.replace(a, b)
n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
n = "".join(ch for ch in n if 32 <= ord(ch) < 127 and ch not in "\"\x27\\")
print(" ".join(n.split())[:32])')
[ -n "$name" ] || { forget; finish error no_name "Name your companion first."; }

# ---- the admin account -------------------------------------------------------
# Made once: if the first start is done again after a later step failed, the
# account it made the first time is kept and its password set again.
if [ -n "$ADD_ADMIN" ]; then
  printf '%s\n' "$apw" | $ADD_ADMIN "$admin" >/dev/null 2>&1 \
    || { forget; finish error admin "The admin account could not be made. Try again."; }
else
  if ! getent passwd "$admin" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash --groups sudo,adm \
      --comment "AetherSeed admin" "$admin" >/dev/null 2>&1 \
      || { forget; finish error admin "The admin account could not be made. Try again."; }
    printf '%s\n' "$admin" > "$ADMIN_MADE"; chmod 600 "$ADMIN_MADE"
  fi
  printf '%s:%s\n' "$admin" "$apw" | chpasswd >/dev/null 2>&1 \
    || { forget; finish error admin "The admin password could not be set. Try again."; }
fi
unset apw
printf '%s\n' "$admin" > "$ADMIN_RECORD" && chmod 644 "$ADMIN_RECORD"

# The admin may sign in over SSH with its password (the operator, 15 Nov 2026: yes,
# simplest in the field) - this account only, whatever the rest of sshd says.
# Checked with sshd -t; a drop-in sshd refuses is taken away again.
if [ -z "$ADD_ADMIN" ]; then
  printf 'Match User %s\n    PasswordAuthentication yes\n' "$admin" > "$SSHD_DROPIN"
  if command -v sshd >/dev/null && sshd -t >/dev/null 2>&1; then
    systemctl reload ssh >/dev/null 2>&1 || systemctl reload sshd >/dev/null 2>&1 || true
  else
    rm -f "$SSHD_DROPIN"
  fi
fi

# ---- the unit's name on the local network -------------------------------------
host=$(printf '%s' "$name" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9-' '-' | sed 's/--*/-/g; s/^-//; s/-$//' | cut -c1-30)
if [ -n "$host" ]; then
  if [ -n "$SET_HOSTNAME" ]; then
    $SET_HOSTNAME "$host" >/dev/null 2>&1 || true
  else
    hostnamectl set-hostname "$host" >/dev/null 2>&1 || true
    if grep -q '^127\.0\.1\.1' /etc/hosts; then
      sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$host/" /etc/hosts
    else
      printf '127.0.1.1\t%s\n' "$host" >> /etc/hosts
    fi
    systemctl enable --now avahi-daemon >/dev/null 2>&1 || true
    systemctl try-restart avahi-daemon >/dev/null 2>&1 || true
  fi
fi

# The steward's own passkey. The Wi-Fi is already up; if this fails the unit
# stays armed, so the first start can be done again.
if ! printf '%s\n' "$own" | python3 "$STEWARD_KEY" own >/dev/null 2>&1; then
  unset own
  finish error steward_key "The steward's passkey could not be set. Try again."
fi
unset own

rm -f "$FLAG" "$ADMIN_MADE"

# ---- the unit's own network, last --------------------------------------------
# The answer first: the phone that sent this is on the setup network and loses
# it when the unit switches. If the switch fails, the unit is armed again and
# keeps its setup network, so the first start can be done once more.
tmp=$(mktemp -p "$(dirname "$RUN_DIR")" .aetherseed-first-start.XXXXXX) &&
  printf '%s\n' ok "$name" "$host" "$net" > "$tmp" && chmod 644 "$tmp" && mv -fT "$tmp" "$RESULT"
echo "first-start: ok $name $host $net"
sleep "${AETHERSEED_SWITCH_DELAY:-4}"
case $net in
  lan)     out=$("$HOTSPOT" off --lan 2>&1) ;;
  visible) out=$(printf '%s\n' "$key" | "$HOTSPOT" on --visible "$name" 2>&1) ;;
  *)       out=$(printf '%s\n' "$key" | "$HOTSPOT" on "$name" 2>&1) ;;
esac
rc=$?
unset key
if [ $rc -ne 0 ]; then
  touch "$FLAG"
  echo "first-start: the unit's own network could not be set up ($(printf '%s' "$out" | tail -1 | cut -c1-160)); armed again, the setup network stays"
fi
exit 0
