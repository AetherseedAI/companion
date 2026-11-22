#!/bin/bash
# AetherSeed Companion installer.
#
#   sudo ./install.sh [--lan] [--kiosk] [--model NAME] [--firewall] [--first-start] [--check]
#
#   --check   only check the prerequisites; change nothing
#   --lan     let the console be reached from your network (default: this
#             device only, http://127.0.0.1:2077)
#   --kiosk   also install the full-screen display service (needs labwc and
#             chromium, as on Raspberry Pi OS with desktop)
#   --model qwen3:1.7b | qwen3:4b | qwen2.5:1.5b
#             the model to serve (default: the one already set on this device,
#             else qwen3:1.7b)
#   --firewall
#             put the unit's firewall in place (services/nftables.conf): the
#             console and SSH from your own network and the unit's Wi-Fi;
#             out, only the clock and, if switched on, Claude. Checked first.
#   --first-start
#             a new unit: when nobody has set it up yet, it waits for its
#             first start and offers the visible Wi-Fi network "AetherSeed"
#             (its key is shown as a QR code on its own screen), so the owner
#             can do the first start from a phone. Never on a unit in use.
#
# Safe to run again. It does not install the Hailo runtime, the driver or the
# model: tools/hailo/ builds and installs those (see docs/INSTALL.md).
set -eu

SRC=$(cd "$(dirname "$0")" && pwd)
APP=/opt/aetherseed
STATE=/var/lib/aetherseed
MODEL=$(sed -n 's/^AETHERSEED_MODEL=//p' /etc/aetherseed/model.env 2>/dev/null | head -1)
WAS_MODEL=$MODEL
MODEL=${MODEL:-qwen3:1.7b}
LAN=0; KIOSK=0; CHECK=0; FIRST=0; FIREWALL=0
while [ $# -gt 0 ]; do
  case $1 in
    --lan) LAN=1 ;; --kiosk) KIOSK=1 ;; --check) CHECK=1 ;; --first-start) FIRST=1 ;; --firewall) FIREWALL=1 ;;
    --model) shift; MODEL=${1:-} ;;
    -h|--help) sed -n 2,26p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case $MODEL in
  qwen3:1.7b)   HEF=qwen3-1.7b;   TOKENIZER=qwen3-1.7b.tokenizer.json ;;
  qwen3:4b)     HEF=qwen3-4b;     TOKENIZER=qwen3-1.7b.tokenizer.json ;;   # Qwen3's one tokenizer
  qwen2.5:1.5b) HEF=qwen2.5-1.5b; TOKENIZER=qwen2.5-instruct-1.5b.tokenizer.json ;;
  *) echo "model not supported by this installer: $MODEL" >&2; exit 2 ;;
esac

fail=0
need() { # need <description> <command...>
  local d=$1; shift
  if "$@" >/dev/null 2>&1; then echo "  ok       $d"; else echo "  MISSING  $d"; fail=1; fi
}

echo "Checking prerequisites"
need "running as root"                      test "$(id -u)" = 0
need "systemd"                              test -d /run/systemd/system
need "python3 (3.11 or newer)"              python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'
need "python3 venv"                         python3 -c 'import venv, ensurepip'
need "curl"                                 command -v curl
if [ $FIREWALL = 1 ]; then need "nftables (for --firewall)"       command -v nft; fi
need "Hailo device (/dev/h1x-0)"            test -e /dev/h1x-0
need "hailortcli"                           command -v hailortcli
need "hailo-ollama"                         command -v hailo-ollama
if [ -e /dev/h1x-0 ] && command -v hailortcli >/dev/null; then
  need "HailoRT 5.4.0 or 5.5.0"             sh -c 'hailortcli --version 2>&1 | grep -Eq "5\.(4|5)\.0"'
fi
need "model $MODEL file in hailo-ollama's store" \
     sh -c "ls /usr/share/hailo-ollama/models/blob/ 2>/dev/null | grep -qi '^$HEF-'"
need "tokenizer $TOKENIZER"                 sh -c "test -e $STATE/$TOKENIZER || test -e $SRC/$TOKENIZER"

if [ $fail = 1 ]; then
  echo
  echo "Some prerequisites are missing. See docs/INSTALL.md, 'Prerequisites'."
  [ $CHECK = 1 ] && exit 1
  echo "Nothing was changed."
  exit 1
fi
[ $CHECK = 1 ] && { echo "All prerequisites met."; exit 0; }

echo "Accounts"
getent group hailo >/dev/null || groupadd --system hailo
id aetherseed >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --create-home \
  --shell /usr/sbin/nologin --comment "AetherSeed Companion" aetherseed
usermod -aG hailo aetherseed

echo "Application -> $APP"
install -d -o root -g root -m 755 "$APP"
( cd "$SRC" && tar --exclude=__pycache__ --exclude='test_*.py' --exclude=.git \
    --exclude=docs --exclude=install.sh --exclude=venv -cf - \
    *.py gui kiosk knowledge library logic tools training requirements.txt ) | tar -x -C "$APP" --no-same-owner
chown -R root:root "$APP"; chmod -R a+rX,go-w "$APP"

echo "Python environment"
[ -x "$APP/venv/bin/python3" ] || python3 -m venv --system-site-packages "$APP/venv"
"$APP/venv/bin/pip" install --quiet -r "$APP/requirements.txt"

echo "Model and state"
install -d -o root -g root -m 755 /etc/aetherseed
echo "AETHERSEED_MODEL=$MODEL" > /etc/aetherseed/model.env
chmod 644 /etc/aetherseed/model.env
install -d -o aetherseed -g aetherseed -m 750 "$STATE"
if [ ! -e "$STATE/$TOKENIZER" ] && [ -e "$SRC/$TOKENIZER" ]; then
  install -o aetherseed -g aetherseed -m 644 "$SRC/$TOKENIZER" "$STATE/"
fi

echo "Services"
UNITS="hailo-ollama aetherseed-proxy aetherseed-warmup aetherseed-gui aetherseed-keepalive"
for u in $UNITS; do
  install -o root -g root -m 644 "$SRC/services/$u.service" "/etc/systemd/system/$u.service"
done
# The console's power-off: it leaves a request in its runtime directory, and
# this root-owned path unit sees it and starts the orderly shutdown.
for u in aetherseed-shutdown.path aetherseed-shutdown.service; do
  install -o root -g root -m 644 "$SRC/services/$u" "/etc/systemd/system/$u"
done
# The console's model switch, the same way: the owner asks, the console leaves
# the model's name, and this root-owned pair checks it and does it
# (tools/model.py). Also at a shell: sudo /opt/aetherseed/tools/model.py set NAME
for u in aetherseed-model.path aetherseed-model.service; do
  install -o root -g root -m 644 "$SRC/services/$u" "/etc/systemd/system/$u"
done
# Locking the image's pi account from the unit's own screen, once the admin's
# password is shown to work (tools/lock_pi_request.py), the same way.
for u in aetherseed-lock-pi.path aetherseed-lock-pi.service; do
  install -o root -g root -m 644 "$SRC/services/$u" "/etc/systemd/system/$u"
done
# A home Wi-Fi from the console (tools/wifi.py): the console leaves the
# network's name and password in a request, this root-owned pair saves it as
# a NetworkManager profile, and tools/hotspot.sh joins it by its rule.
for u in aetherseed-wifi.path aetherseed-wifi.service aetherseed-hotspot.service; do
  install -o root -g root -m 644 "$SRC/services/$u" "/etc/systemd/system/$u"
done
# (aetherseed-hotspot.service, the rule, is installed here and enabled by
# tools/hotspot.sh on or by the first home network tools/wifi.py saves.)
# More than one person on the unit (tools/people.py, the owner's to run): the
# unit each person's own proxy starts from - installed, enabled for nobody -
# and the two folders their roots and passkey records live in. They are made
# now so the console and the proxy, started below, see them where they are.
install -o root -g root -m 644 "$SRC/services/aetherseed-proxy@.service" \
  "/etc/systemd/system/aetherseed-proxy@.service"
install -d -o aetherseed -g aetherseed -m 700 /var/lib/aetherseed-keys
install -d -o root -g root -m 755 /var/lib/aetherseed-people /etc/aetherseed/people
install -d /etc/systemd/system/hailo-ollama.service.d
install -o root -g root -m 644 "$SRC/services/hailo-ollama.hailort540.conf" \
  /etc/systemd/system/hailo-ollama.service.d/hailort-540.conf
install -o root -g root -m 644 "$SRC/services/99-aetherseed-hailo1x.rules" /etc/udev/rules.d/
# The clock from the network when there is one (21 Nov 2026); the firewall
# lets only the clock service's own user ask.
install -d /etc/systemd/timesyncd.conf.d
install -o root -g root -m 644 "$SRC/services/timesyncd-aetherseed.conf" \
  /etc/systemd/timesyncd.conf.d/aetherseed.conf
systemctl enable systemd-timesyncd >/dev/null 2>&1 || true
systemctl try-restart systemd-timesyncd >/dev/null 2>&1 || true
if [ $LAN = 0 ]; then
  install -d /etc/systemd/system/aetherseed-gui.service.d
  printf '[Service]\nEnvironment=AETHERSEED_GUI_BIND=127.0.0.1\n' \
    > /etc/systemd/system/aetherseed-gui.service.d/bind.conf
else
  rm -f /etc/systemd/system/aetherseed-gui.service.d/bind.conf
fi
if [ $KIOSK = 1 ]; then
  id aetherseed-kiosk >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin \
    --comment "AetherSeed Companion screen" --groups video,render,input aetherseed-kiosk
  for u in aetherseed-kiosk aetherseed-kiosk-watch; do
    install -o root -g root -m 644 "$SRC/services/$u.service" "/etc/systemd/system/$u.service"
  done
  UNITS="$UNITS aetherseed-kiosk aetherseed-kiosk-watch"
  # The screen is the companion's. On Raspberry Pi OS with desktop a login
  # screen (a display manager) holds the display, and the kiosk cannot start
  # (found on a fresh unit, 21 Nov 2026): it is switched off and the unit
  # boots to the console. The desktop comes back with
  #   sudo systemctl enable lightdm && sudo systemctl set-default graphical.target
  if systemctl is-enabled display-manager >/dev/null 2>&1 \
     || [ "$(systemctl get-default 2>/dev/null)" = graphical.target ]; then
    echo "  the screen is the companion's: the desktop login is switched off (takes effect at the next start)"
    systemctl disable display-manager >/dev/null 2>&1 || true
    systemctl set-default multi-user.target >/dev/null 2>&1 || true
    KIOSK_REBOOT=1
  fi
fi
udevadm control --reload-rules
udevadm trigger --subsystem-match=hailo1x || true
systemctl daemon-reload

echo "Manual"
( cd "$APP" && HOME="$STATE" "$APP/venv/bin/python3" -m logic.manual ) || \
  echo "  (manual not built; the console still works)"

# A service already running keeps the model it read at its start: on a unit
# whose model this run changed, the keep-alive went on asking for the old one
# every three minutes and the chip swapped models under every talk (a unit,
# 14 Nov 2026). So what serves the model starts again when it changed - and
# in this order, because restarting the server while a model loads leaves the
# chip unanswering until a reboot ("LLM not loaded", HAILO_TIMEOUT; a unit,
# 16 Nov 2026, where the warm-up had asked for the new model first): first
# everything that asks for a model stops, then the server starts again with
# nothing loading, then (below) the rest starts and asks.
PEOPLE_UP=""
if [ -n "$WAS_MODEL" ] && [ "$WAS_MODEL" != "$MODEL" ]; then
  echo "  the model changed ($WAS_MODEL -> $MODEL): restarting what serves it"
  PEOPLE_UP=$(systemctl list-units 'aetherseed-proxy@*' --state=active --no-legend --plain 2>/dev/null | awk '{print $1}')
  systemctl stop aetherseed-keepalive aetherseed-warmup aetherseed-proxy $PEOPLE_UP 2>/dev/null || true
  systemctl restart hailo-ollama
  for _ in $(seq 1 60); do
    curl -s -m 2 -o /dev/null http://127.0.0.1:8000/api/tags && break
    sleep 1
  done
fi

echo "Starting"
systemctl enable --now $UNITS aetherseed-shutdown.path aetherseed-model.path aetherseed-lock-pi.path aetherseed-wifi.path
if [ -n "$PEOPLE_UP" ]; then
  systemctl start $PEOPLE_UP || true
fi
# what the console may offer to switch to: this build's models that have a
# measured ceiling, a file in the store and a tokenizer on the unit
"$APP/venv/bin/python3" "$APP/tools/model.py" choices || echo "  (the list of models was not written)"

if [ $FIREWALL = 1 ]; then
  echo "Firewall"
  if nft -c -f "$SRC/services/nftables.conf"; then
    install -o root -g root -m 644 "$SRC/services/nftables.conf" /etc/nftables.conf
    systemctl enable nftables >/dev/null 2>&1 || true
    nft -f /etc/nftables.conf && echo "  in place: $(nft list ruleset | grep -c accept) accept rules"
  else
    echo "  the rules did not pass nft's check: the firewall was left as it was"
  fi
fi

if [ $FIRST = 1 ]; then
  # Only a unit nobody has set up: the companion has no name yet.
  if "$APP/venv/bin/python3" -c "import json,sys; sys.exit(0 if json.load(open('$STATE/.aetherseed/companion.json')).get('name') else 1)" 2>/dev/null; then
    echo "First start: this unit is already set up - nothing armed."
  else
    echo "First start"
    install -d -o root -g root -m 755 /etc/aetherseed
    touch /etc/aetherseed/first-start
    if bash "$APP/tools/hotspot.sh" setup; then
      echo "  armed: the network \"AetherSeed\" is up; its key is on the unit's own screen"
    else
      echo "  armed, but the setup network did not come up (no Wi-Fi?): do the first start at the unit's screen"
    fi
  fi
fi

echo
echo "Done. Check:  systemctl --failed   and   journalctl -u aetherseed-proxy -n 20"
echo "Console:      http://127.0.0.1:2077"
if [ "${KIOSK_REBOOT:-0}" = 1 ]; then
  echo "Restart the unit once (sudo reboot) so the screen comes up on the companion."
fi
