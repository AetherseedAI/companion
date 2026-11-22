#!/bin/bash
# After the restart that follows tools/hailo/install.sh: is the chip on
# HailoRT 5.5.0? Then the companion is let start again.
#   sudo bash tools/hailo/check.sh
set -u
step() { echo "== $(date '+%F %T') $*"; }
fail() { step "NOT READY: $* (the companion stays held; see tools/hailo/install.sh for the way back)"; exit 1; }
[ "$(id -u)" = 0 ] || fail "run as root (sudo)"
step "driver, device, firmware"
lsmod | grep -q hailo1x_pci || fail "the driver is not loaded"
echo "  driver $(cat /sys/module/hailo1x_pci/version)"
[ -e /dev/h1x-0 ] || fail "no /dev/h1x-0"
hailortcli fw-control identify | grep -E "Firmware Version|Board Name|Architecture"
hailortcli fw-control identify | grep -q "Firmware Version: 5.5.0" || fail "the firmware is not 5.5.0"
step "the companion may start again"
rm -f /etc/systemd/system/aetherseed-proxy.service.d/hailort-hold.conf
systemctl daemon-reload
if systemctl cat hailo-ollama >/dev/null 2>&1; then
  systemctl restart hailo-ollama; sleep 8
  systemctl is-active hailo-ollama >/dev/null || fail "hailo-ollama does not start (journalctl -u hailo-ollama)"
  curl -s -m 20 http://127.0.0.1:8000/api/tags | grep -oE '"name":"[^"]*"' | sed 's/^/  model /'
  systemctl start aetherseed-keepalive aetherseed-proxy >/dev/null 2>&1 || true
  echo "  next: sudo ./install.sh (again, if the companion was installed before)"
else
  echo "  hailo-ollama is not set up yet: next, ./install.sh sets it up"
fi
step "ready"
