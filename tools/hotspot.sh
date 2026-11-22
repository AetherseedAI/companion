#!/bin/bash
# The unit's own Wi-Fi.
#
# "if no LAN was connected, the wifi would emmit ssid
# a unit and with the correct passkey I could access the gui through the device
# I connected to the companions wifi" - "it is to use as the companion screen,
# not support, the device should remain private."
#
# A phone or laptop that joins the network named after the companion, with the
# steward's passkey, opens the console at http://10.42.0.1:2077 - the same
# page as on the unit's own screen. Tested on a unit, with the steward's
# iPhone: it joined, opened the console, and one turn was stored ("its great").
#
#   sudo tools/hotspot.sh on [NAME]    set it up; NAME defaults to the
#                                      companion's name. The passkey is read
#                                      from standard input (one line), or
#                                      asked for without echo at a terminal.
#   sudo tools/hotspot.sh off          take it down and remove it
#        tools/hotspot.sh status       is it set up, is it up, who is on it
#   sudo tools/hotspot.sh sync         apply the rule below once, now
#   sudo tools/hotspot.sh start        the same, after giving a cable time to
#                                      find its link (what `watch` begins with)
#   sudo tools/hotspot.sh watch        apply it, and again whenever a cable's
#                                      link changes (aetherseed-hotspot.service)
#        tools/hotspot.sh --check NAME validate NAME and a passkey on standard
#                                      input; changes nothing (the tests)
#
# THE RULE. The radio is switched off while a network cable has a link, and
# the unit's Wi-Fi comes up when no cable has one - at start, and within
# seconds of the cable being pulled.
#
# A HOME WI-FI (16 Nov 2026: "The unit should be able to connect to the wifi
# regardless"). When one has been given (tools/wifi.py, from the console:
# profile `aetherseed-home`), the order is: a cable; else the home Wi-Fi;
# else the unit's own hidden network. The home Wi-Fi is tried, and if it does
# not answer within JOIN_WAIT seconds the unit's own network comes up again,
# so a unit is never left unreachable (a changed router password, a router
# switched off). From its own network it tries the home one again every RETRY
# seconds, but never while a phone is on its own network - someone may be
# setting it up just then. A link is the cable's own (the port's
# carrier), not whether the network behind it answers: a cable into a dead
# switch still counts as a cable.
#
# What it is: one NetworkManager profile, `aetherseed-hotspot`, that
# NetworkManager never brings up by itself; `watch` does, by the rule.
# NetworkManager runs the access point
# (wpa_supplicant) and hands out addresses (its own dnsmasq, 10.42.0.10-254).
# The firewall (services/nftables.conf) admits the address request and the
# console port from wlan0 and nothing else; it does not pass a phone's traffic
# on to the cable network, and there is no name service on the unit's Wi-Fi,
# so a phone will say "no internet". That is the design.
#
# The passkey is kept in the profile only (root, mode 600), never in the
# build, a log or the cartridge. Until whoever held it was at the
# console as the steward. Now it gets a phone onto the unit's network as a
# guest, and the steward signs in there with his name and this passkey: its
# hash - never the passkey - goes to /etc/aetherseed/steward.key
# (tools/steward_key.py), unless he has set a passkey of his own.
set -u
export PATH=$PATH:/usr/sbin:/sbin
HERE=$(cd "$(dirname "$0")" && pwd)
STEWARD_KEY_TOOL=${AETHERSEED_STEWARD_KEY_TOOL:-$HERE/steward_key.py}

PROFILE=aetherseed-hotspot
# THE SETUP NETWORK (21 Nov 2026, the operator: "the unit can be AetherSeed on the
# wifi unhidden until first connection, then the user can decide whether to
# have it broadcasting hidden, not hidden or LAN only"). A unit armed for its
# first start, with no network of its own yet, shows a VISIBLE network named
# "AetherSeed". It is WPA2 with a key made on the unit and shown on its own
# screen (with a code a phone can scan), because the first start sends the
# owner's passkeys and admin password over it: an open network would let
# anyone nearby read them. At the first start the owner picks the unit's own
# network - hidden, visible, or none (LAN only) - and the setup network goes.
SETUP_PROFILE=aetherseed-setup
SETUP_SSID=AetherSeed
SETUP_KEY=${AETHERSEED_SETUP_KEY:-/etc/aetherseed/setup-wifi.key}
ARMED_FLAG=${AETHERSEED_FIRST_START_FLAG:-/etc/aetherseed/first-start}
# Until the unit has a network of its own, the rule serves the setup one.
if ! nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$PROFILE" \
   && nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$SETUP_PROFILE"; then
  PROFILE=$SETUP_PROFILE
fi
ADDRESS=10.42.0.1/24
CHANNEL=6
WATCHER=aetherseed-hotspot.service
NET_DIR=${AETHERSEED_NET_DIR:-/sys/class/net}
SETTLE=${AETHERSEED_SETTLE:-30}       # seconds a cable is given to find its link at start
STATUS_URL=${AETHERSEED_STATUS_URL:-http://127.0.0.1:8001/aetherseed/status}
HOME_PROFILE=aetherseed-home
JOIN_WAIT=${AETHERSEED_JOIN_WAIT:-40}  # seconds the home Wi-Fi is given to answer
RETRY=${AETHERSEED_HOME_RETRY:-300}    # seconds before it is tried again from the unit's own network
TICK=${AETHERSEED_TICK:-60}            # how often `watch` looks again with no change of link
WIFI_STATE=${AETHERSEED_WIFI_STATE:-/run/aetherseed-wifi-state}
LOCK=${AETHERSEED_HOTSPOT_LOCK:-/run/aetherseed-hotspot.lock}

die() { echo "hotspot: $*" >&2; exit 2; }

# A network name: 1-32 bytes, printable, no quote or backslash to trip a shell.
check_name() {
  local n=$1 bytes
  bytes=$(printf '%s' "$n" | wc -c)
  [ "$bytes" -ge 1 ] && [ "$bytes" -le 32 ] || return 1
  printf '%s' "$n" | LC_ALL=C grep -q '[^ -~]' && return 1
  case $n in *\"*|*\'*|*\\*) return 1 ;; esac
  case $n in " "*|*" ") return 1 ;; esac
  return 0
}

# A WPA2 passkey: 8-63 printable ASCII characters.
check_passkey() {
  local k=$1 len=${#1}
  [ "$len" -ge 8 ] && [ "$len" -le 63 ] || return 1
  printf '%s' "$k" | LC_ALL=C grep -q '[^ -~]' && return 1
  return 0
}

read_passkey() {
  local k=""
  if [ -t 0 ]; then
    read -r -s -p "Passkey for the unit's Wi-Fi (8-63 characters): " k; echo >&2
  else
    IFS= read -r k || true
  fi
  printf '%s' "$k"
}

companion_name() {
  curl -s --max-time 5 "$STATUS_URL" 2>/dev/null | python3 -c '
import json, sys
try:
    c = json.load(sys.stdin).get("companion") or {}
    print(c.get("name") or "" if c.get("configured") else "")
except Exception:
    print("")'
}

# Has a network cable a link? A wired port of the unit itself (not the
# loopback, not the radio, not a bridge or a tunnel) whose carrier is 1. A
# port that is switched off cannot be read, and counts as no link.
cable_linked() {
  local d
  for d in "$NET_DIR"/*; do
    [ -e "$d/device" ] || continue
    [ -e "$d/wireless" ] || [ -e "$d/phy80211" ] && continue
    [ "$(cat "$d/type" 2>/dev/null)" = 1 ] || continue
    [ "$(cat "$d/carrier" 2>/dev/null)" = 1 ] && return 0
  done
  return 1
}

set_up() { nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$PROFILE"; }
is_up()  { nmcli -t -f NAME connection show --active 2>/dev/null | grep -qx "$PROFILE"; }
home_saved() { nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$HOME_PROFILE"; }
home_up()    { nmcli -t -f NAME connection show --active 2>/dev/null | grep -qx "$HOME_PROFILE"; }

# What the radio serves, for the console: key=value lines, written in /run
# (root's) and renamed into place. Where it cannot be written (a test, a user
# without root), it is simply not written.
state_get() { sed -n "s/^$1=//p" "$WIFI_STATE" 2>/dev/null | head -1; }
note() {   # note <serving> [home_result]
  local d tmp failed_at
  d=$(dirname "$WIFI_STATE")
  [ -w "$d" ] || return 0
  failed_at=$(state_get home_failed_at)
  case ${2:-} in
    failed) failed_at=$(date +%s) ;;
    ok) failed_at="" ;;
  esac
  tmp=$(mktemp "$d/.aetherseed-wifi-state.XXXXXX" 2>/dev/null) || return 0
  {
    echo "serving=$1"
    echo "at=$(date +%s)"
    [ -n "${2:-}" ] && echo "home_last=$2" || echo "home_last=$(state_get home_last)"
    echo "home_failed_at=$failed_at"
  } > "$tmp"
  chmod 644 "$tmp"
  mv -f "$tmp" "$WIFI_STATE"
}

# The home Wi-Fi may be tried now: never tried, or the last try failed RETRY
# seconds ago or more and nobody is on the unit's own network.
may_try_home() {
  local failed now
  failed=$(state_get home_failed_at)
  [ -z "$failed" ] && return 0
  now=$(date +%s)
  [ $((now - failed)) -ge "$RETRY" ] || return 1
  if is_up && [ "$(iw dev wlan0 station dump 2>/dev/null | grep -c '^Station')" -gt 0 ]; then
    return 1
  fi
  return 0
}

own_up() {
  set_up || return 1
  is_up && return 0
  nmcli radio wifi on
  for _ in 1 2 3 4 5 6; do
    nmcli connection up "$PROFILE" >/dev/null 2>&1 && break
    sleep 2
  done
  is_up
}

# The rule, applied once. Says what it did only when it did something.
sync_rule() {
  set_up || home_saved || return 0    # no Wi-Fi of its own and none given: nothing to do
  # Armed, with only the setup network: it stays up whatever else is linked,
  # until the first start (21 Nov 2026: "AetherSeed on the wifi unhidden until
  # first connection"). The first start removes it.
  if [ "$PROFILE" = "$SETUP_PROFILE" ] && [ -e "$ARMED_FLAG" ] && set_up; then
    if ! is_up && ! own_up; then
      echo "hotspot: the setup network would not come up" >&2; return 1
    fi
    note own
    return 0
  fi
  if cable_linked; then
    if is_up || home_up || [ "$(nmcli radio wifi 2>/dev/null)" = enabled ]; then
      is_up && nmcli connection down "$PROFILE" >/dev/null 2>&1
      home_up && nmcli connection down "$HOME_PROFILE" >/dev/null 2>&1
      nmcli radio wifi off
      echo "hotspot: a cable is linked - the radio is off"
    fi
    note cable
    return 0
  fi
  if home_saved; then
    if home_up; then note home; return 0; fi
    if may_try_home; then
      nmcli radio wifi on
      is_up && nmcli connection down "$PROFILE" >/dev/null 2>&1
      if nmcli --wait "$JOIN_WAIT" connection up "$HOME_PROFILE" >/dev/null 2>&1 && home_up; then
        echo "hotspot: no cable is linked - the unit is on the home Wi-Fi"
        note home ok
        return 0
      fi
      nmcli connection down "$HOME_PROFILE" >/dev/null 2>&1
      echo "hotspot: the home Wi-Fi did not answer - the unit's own network comes up" >&2
      note own failed
    fi
  fi
  set_up || return 0
  if ! is_up; then
    if own_up; then echo "hotspot: no cable is linked - the unit's Wi-Fi is up"
    else echo "hotspot: no cable is linked - the unit's Wi-Fi would not come up" >&2; return 1
    fi
  fi
  note own
}

# One rule at a time: a change of link, the clock and the console may all ask
# at once. Without a lock file it can open (a test), the rule simply runs.
sync_locked() {
  local rc
  if { exec 9>>"$LOCK"; } 2>/dev/null; then
    flock 9
    sync_rule; rc=$?
    exec 9>&-
    return $rc
  fi
  sync_rule
}

# The rule at start. A cable that is in has no link yet when the unit comes
# up: on a unit, the port found its link 15 seconds after this
# began, and for 14 of them the unit's Wi-Fi was up with the cable in.
# So "no cable" is believed at start only once it has stayed so for SETTLE
# seconds. With no cable, the Wi-Fi is that much later at start.
start_rule() {
  local waited=0
  # A unit armed for its first start with no network yet (a card made into
  # a source, copied, and started here): its setup network is made now, with
  # a key of its own.
  if [ -e "$ARMED_FLAG" ] && ! nmcli -t -f NAME connection show 2>/dev/null | grep -qx aetherseed-hotspot \
     && ! nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$SETUP_PROFILE"; then
    "$0" setup >/dev/null 2>&1 && PROFILE=$SETUP_PROFILE
  fi
  if set_up; then
    while ! cable_linked && [ "$waited" -lt "$SETTLE" ]; do
      sleep 1
      waited=$((waited + 1))
    done
  fi
  sync_locked
}

case ${1:-} in
  sync)
    [ "$(id -u)" = 0 ] || die "run with sudo"
    sync_locked
    ;;

  start)
    [ "$(id -u)" = 0 ] || die "run with sudo"
    start_rule
    ;;

  watch)
    [ "$(id -u)" = 0 ] || die "run with sudo"
    start_rule
    # Every change of a link, as the kernel reports it. Changes of the radio
    # itself are passed over - the rule causes those. A link that flaps is
    # read once it has settled.
    # And every TICK seconds with no change of link: a home Wi-Fi that went
    # away, or one to try again from the unit's own network.
    ( while sleep "$TICK"; do sync_locked; done ) &
    ip -o monitor link | while read -r _ dev _; do
      dev=${dev%:}; dev=${dev%@*}
      case $dev in wlan*|lo|"") continue ;; esac
      sleep 3
      while read -r -t 0.2 _; do :; done
      sync_locked
    done
    ;;

  --check)
    check_name "${2:-}" || die "not a usable network name (1-32 plain characters)"
    check_passkey "$(read_passkey)" || die "not a usable passkey (8-63 plain characters)"
    echo ok
    ;;

  setup)
    # The setup network, on a unit armed for its first start. The key is made
    # once, readable by root and the console's group (the console shows it on
    # the unit's own screen only), and goes with the first start.
    [ "$(id -u)" = 0 ] || die "run with sudo"
    [ -e "$ARMED_FLAG" ] || die "this unit is not armed for a first start: no setup network"
    if nmcli -t -f NAME connection show | grep -qx aetherseed-hotspot; then
      die "this unit already has a network of its own: no setup network"
    fi
    if [ ! -s "$SETUP_KEY" ]; then
      # 10 letters and digits, none that look alike (no 0/O, 1/l/I)
      umask 027
      tr -dc 'abcdefghijkmnpqrstuvwxyz23456789' < /dev/urandom | head -c 10 > "$SETUP_KEY" \
        || die "the setup key could not be made"
      chgrp aetherseed "$SETUP_KEY" 2>/dev/null || true
      chmod 640 "$SETUP_KEY"
    fi
    systemctl cat "$WATCHER" >/dev/null 2>&1 \
      || die "$WATCHER is not installed: without it the radio would not follow the cable"
    systemctl enable --now wpa_supplicant >/dev/null 2>&1 || die "wpa_supplicant would not start"
    nmcli connection delete "$SETUP_PROFILE" >/dev/null 2>&1
    nmcli connection add type wifi ifname wlan0 con-name "$SETUP_PROFILE" ssid "$SETUP_SSID" \
      connection.autoconnect no \
      802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel "$CHANNEL" \
      802-11-wireless.hidden no \
      wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
      wifi-sec.psk "$(cat "$SETUP_KEY")" \
      ipv4.method shared ipv4.addresses "$ADDRESS" ipv6.method disabled >/dev/null \
      || die "the setup profile could not be written"
    systemctl enable "$WATCHER" >/dev/null 2>&1
    systemctl restart "$WATCHER" || die "$WATCHER would not start"
    echo "hotspot: the setup network \"$SETUP_SSID\" is set up (visible; its key is on the unit's own screen)"
    ;;

  on)
    [ "$(id -u)" = 0 ] || die "run with sudo"
    hidden=yes
    if [ "${2:-}" = "--visible" ]; then hidden=no; shift; fi
    name=${2:-$(companion_name)}
    [ -n "$name" ] || die "the companion has no name yet - name it on the unit's screen first, or give one"
    check_name "$name" || die "not a usable network name (1-32 plain characters): $name"
    key=$(read_passkey)
    check_passkey "$key" || die "not a usable passkey (8-63 plain characters)"
    # Another saved Wi-Fi network would be joined instead of this one being
    # put up (found on a unit: a home network from her first setup).
    PROFILE=aetherseed-hotspot
    others=$(nmcli -t -f NAME,TYPE connection show | grep ':802-11-wireless$' | grep -v "^$PROFILE:" | grep -v "^$HOME_PROFILE:" | grep -v "^$SETUP_PROFILE:" | cut -d: -f1)
    [ -z "$others" ] || die "another Wi-Fi network is saved on this unit ($others); remove it first: nmcli connection delete NAME"
    systemctl cat "$WATCHER" >/dev/null 2>&1 \
      || die "$WATCHER is not installed (services/, INSTALL 13): without it the radio would not follow the cable"
    systemctl enable --now wpa_supplicant >/dev/null 2>&1 || die "wpa_supplicant would not start"
    nmcli connection delete "$PROFILE" >/dev/null 2>&1
    nmcli connection add type wifi ifname wlan0 con-name "$PROFILE" ssid "$name" \
      connection.autoconnect no \
      802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel "$CHANNEL" \
      802-11-wireless.hidden "$hidden" \
      wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
      wifi-sec.psk "$key" \
      ipv4.method shared ipv4.addresses "$ADDRESS" ipv6.method disabled >/dev/null \
      || die "the profile could not be written"
    # The network is HIDDEN (the operator, 15 Nov 2026): it is not announced, so a
    # phone must be given both its name and its passkey to join. (A phone
    # that has joined once asks for it by name, so the name is not a secret
    # from someone listening nearby; it keeps it off every passer-by's list.)
    # The Wi-Fi passkey is NOT the steward's sign-in any more (code review
    # everyone given the Wi-Fi holds it. The
    # steward's own passkey is set at the first start, or with
    # `sudo tools/steward_key.py own`. Until one is set, every phone is a guest.
    unset key
    # The unit has a network of its own now: the setup one goes, with its key.
    nmcli connection down "$SETUP_PROFILE" >/dev/null 2>&1
    nmcli connection delete "$SETUP_PROFILE" >/dev/null 2>&1
    rm -f "$SETUP_KEY"
    # From here the rule decides: up now if no cable is linked, off if one is.
    systemctl enable "$WATCHER" >/dev/null 2>&1
    systemctl restart "$WATCHER" || die "$WATCHER would not start"
    sleep 4
    "$0" status
    ;;

  off)
    # No network of its own (LAN only). Refused on a unit with no cable link
    # and no home Wi-Fi saved: it could not be reached at all afterwards.
    [ "$(id -u)" = 0 ] || die "run with sudo"
    if [ "${2:-}" = "--lan" ] && ! cable_linked && ! home_saved; then
      die "no cable is linked and no home Wi-Fi is saved: LAN only would leave the unit unreachable"
    fi
    systemctl disable --now "$WATCHER" >/dev/null 2>&1
    for p in aetherseed-hotspot "$SETUP_PROFILE"; do
      nmcli connection down "$p" >/dev/null 2>&1
      nmcli connection delete "$p" >/dev/null 2>&1
    done
    rm -f "$SETUP_KEY"
    if home_saved; then
      # a home Wi-Fi stays, and the rule keeps joining it
      systemctl enable --now "$WATCHER" >/dev/null 2>&1
      "$0" status
      exit 0
    fi
    nmcli radio wifi off
    systemctl disable --now wpa_supplicant >/dev/null 2>&1
    sysctl -q -w net.ipv4.ip_forward=0
    "$0" status
    ;;

  can-lan)
    # LAN only is possible: a cable has a link, or a home Wi-Fi is saved.
    if cable_linked || home_saved; then echo "hotspot: LAN only is possible"; exit 0; fi
    echo "hotspot: no cable is linked and no home Wi-Fi is saved"; exit 1
    ;;

  status)
    if ! nmcli -t -f NAME connection show | grep -qx "$PROFILE"; then
      echo "hotspot: not set up"; exit 0
    fi
    ssid=$(nmcli -g 802-11-wireless.ssid connection show "$PROFILE")
    if nmcli -t -f NAME connection show --active | grep -qx "$PROFILE"; then
      addr=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
      n=$(iw dev wlan0 station dump 2>/dev/null | grep -c '^Station')
      echo "hotspot: up - network \"$ssid\", console at http://$addr:2077, $n device(s) joined"
    else
      echo "hotspot: set up as \"$ssid\" but not up"
    fi
    # Which rule this unit runs: a unit set up under is up at every
    # start, cable or no cable, until it is given this one.
    if systemctl is-active --quiet "$WATCHER" 2>/dev/null; then
      if cable_linked; then echo "hotspot: only while no cable is linked - a cable is linked now, the radio is $(nmcli radio wifi 2>/dev/null)"
      else echo "hotspot: only while no cable is linked - none is linked now"
      fi
    else
      echo "hotspot: the cable rule is not running on this unit ($WATCHER)"
    fi
    ;;

  *)
    sed -n '2,/^set -u/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
