#!/bin/bash
# Lock the image's own "pi" account, once the unit's admin account is known to
# work (the operator, 15 Nov 2026: "after the new admin is confirmed the pi account
# should be locked").
#
#   sudo /opt/aetherseed/tools/lock_default.sh        run AS THE ADMIN
#
# Being run proves the admin works: signed in, and sudo took its password.
# So it refuses unless it was started through sudo by the admin that the
# first start made (/etc/aetherseed/admin-account), and never by pi itself.
# The pi account is locked and expired: no password, no SSH key, no login.
# Nothing is deleted - its home folder stays. The way back, as the admin:
#   sudo usermod -U -e "" pi
set -u
OLD=${AETHERSEED_DEFAULT_ACCOUNT:-pi}
RECORD=${AETHERSEED_ADMIN_RECORD:-/etc/aetherseed/admin-account}
LOCK=${AETHERSEED_LOCK_TOOL:-usermod}          # a stand-in for the tests
[ "$(id -u)" = 0 ] || { echo "run it with sudo, as the admin"; exit 2; }
admin=$(cat "$RECORD" 2>/dev/null | head -1)
[ -n "$admin" ] || { echo "no admin account is recorded on this unit (first start makes one): nothing locked"; exit 1; }
caller=${SUDO_USER:-}
[ -n "$caller" ] || { echo "run it with sudo from the admin's own login, not as root: nothing locked"; exit 1; }
[ "$caller" != "$OLD" ] || { echo "run it as the admin ($admin), not as $OLD: nothing locked"; exit 1; }
[ "$caller" = "$admin" ] || { echo "run it as the admin ($admin), not as $caller: nothing locked"; exit 1; }
if [ -z "${AETHERSEED_LOCK_TOOL:-}" ]; then
  id -nG "$admin" | tr ' ' '\n' | grep -qx sudo || { echo "$admin is not in the sudo group: nothing locked"; exit 1; }
  getent passwd "$OLD" >/dev/null || { echo "there is no $OLD account: nothing to lock"; exit 0; }
fi
$LOCK -L -e 1 "$OLD" || { echo "could not lock $OLD"; exit 1; }
echo "locked: $OLD (no password, no key, no login; its files stay). Way back: sudo usermod -U -e \"\" $OLD"
