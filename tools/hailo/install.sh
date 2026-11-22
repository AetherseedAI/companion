#!/bin/bash
# Put the HailoRT 5.5.0 that tools/hailo/build.sh made into the running
# system, in place of whatever Hailo runtime the unit has (none, Raspberry
# Pi's h10-hailort 5.1.x, or Hailo's 5.4.0 packages). Ends before the reboot;
# after it, tools/hailo/check.sh checks the chip.
#
#   sudo bash tools/hailo/install.sh [FOLDER]      default /var/tmp/hailort-5.5.0
#
# The companion's memory is not touched. Its proxies stay off until the unit
# has restarted (a drop-in that check.sh removes).
# WAY BACK: the files it replaces are archived in FOLDER/before/, together
# with any Hailo .deb packages found in apt's cache; reinstall those with
# sudo dpkg -i FOLDER/before/*.deb, remove the 5.5.0 driver with
# sudo dkms remove hailo1x_pci/5.5.0 --all, and restart.
set -u
W=${1:-/var/tmp/hailort-5.5.0}; ST=$W/stage; K=$W/before; V=5.5.0; KV=$(uname -r)
B=/usr/share/hailo-ollama/models/blob
step() { echo "== $(date '+%F %T') $*"; }
fail() { step "STOPPED: $*"; exit 1; }
[ "$(id -u)" = 0 ] || fail "run as root (sudo)"

step "checks before anything (kernel $KV)"
command -v dkms >/dev/null || fail "dkms is not installed (sudo apt install dkms)"
[ -d "/lib/modules/$KV/build" ] || fail "no kernel headers for $KV: the driver cannot be built"
[ -x "$ST/usr/bin/hailo-ollama" ] || fail "no staged build in $W: run tools/hailo/build.sh first"
ls "$ST"/usr/lib/*/libhailort.so."$V" >/dev/null 2>&1 || ls "$ST"/usr/lib/libhailort.so."$V" >/dev/null 2>&1 || fail "no libhailort $V in $W"
( cd "$W" && sha256sum -c --quiet sha256.txt ) || fail "a downloaded file does not match its sum"

step "the companion held across the restart"
mkdir -p /etc/systemd/system/aetherseed-proxy.service.d
printf '[Unit]\n# HailoRT %s being installed: held until tools/hailo/check.sh\nConditionPathExists=/nonexistent/hailort-hold\n' "$V" \
  > /etc/systemd/system/aetherseed-proxy.service.d/hailort-hold.conf
systemctl daemon-reload
systemctl stop aetherseed-keepalive aetherseed-proxy 'aetherseed-proxy@*' hailo-ollama >/dev/null 2>&1 || true

step "way back: archive what is there now"
mkdir -p "$K"
tar czf "$K/hailo-files.tgz" --ignore-failed-read /usr/bin/hailortcli /usr/bin/hailo-ollama /usr/lib/libhailort.so* \
    /usr/lib/aarch64-linux-gnu/libhailort.so* /usr/lib/cmake/HailoRT /lib/firmware/hailo /etc/modprobe.d/hailo1x_pci.conf \
    /lib/udev/rules.d/51-hailo-pcie-udev.rules /usr/share/hailo-ollama/models/manifests 2>&1 | grep -v "Removing leading" || true
cp -n /var/cache/apt/archives/*hailo*.deb "$K/" 2>/dev/null || true
dpkg -l | awk '/^ii/ && /hailo/ {print $2, $3}' | tee "$K/packages.txt"
dkms status 2>/dev/null | tee "$K/dkms.txt"

step "remove the Hailo packages that are installed"
PKGS=$(dpkg -l | awk '/^ii/ && /hailo/ {print $2}' | grep -E '^(hailo-gen-ai-model-zoo|python3-h10-hailort|h10-hailort|hailort|h10-hailort-pcie-driver|hailort-pcie-driver)$' | tr '\n' ' ')
if [ -n "$PKGS" ]; then
  apt-mark unhold $PKGS >/dev/null 2>&1 || true
  dpkg -r $PKGS || fail "dpkg -r $PKGS"
fi
for old in $(dkms status 2>/dev/null | sed -n 's#^hailo1x_pci/\([^,:]*\).*#\1#p' | sort -u); do
  [ "$old" = "$V" ] || dkms remove "hailo1x_pci/$old" --all
done
rm -f /lib/modules/"$KV"/kernel/drivers/misc/hailo1x_pci.ko*

step "HailoRT $V, hailortcli, hailo-ollama"
install -m 755 "$ST/usr/bin/hailortcli" "$ST/usr/bin/hailo-ollama" /usr/bin/
for d in "$ST/usr/lib/aarch64-linux-gnu" "$ST/usr/lib"; do
  [ -d "$d" ] && cp -a "$d/." "$(echo "$d" | sed "s#^$ST##")/"
done
ldconfig
mkdir -p /usr/share/hailo-ollama/models
cp -a "$ST/usr/share/hailo-ollama/models/manifests" /usr/share/hailo-ollama/models/
chmod -R go-w /usr/share/hailo-ollama
hailortcli --version
ldd /usr/bin/hailo-ollama | grep -q "not found" && fail "hailo-ollama is missing a library"

step "model files"
mkdir -p "$B"
for f in "$W"/model/*.hef; do
  n=$(basename "$f"); install -m 644 "$f" "$B/$n"
  ( cd "$B" && sha256sum "$n" | cut -d' ' -f1 > "$n.sha256" )
done
ls -l "$B"

step "the Qwen3 tokenizer for the companion"
install -d -m 755 /var/lib/aetherseed
install -m 644 "$W/qwen3-1.7b.tokenizer.json" /var/lib/aetherseed/qwen3-1.7b.tokenizer.json
id aetherseed >/dev/null 2>&1 && chown aetherseed: /var/lib/aetherseed/qwen3-1.7b.tokenizer.json

step "firmware $V"
rm -rf /lib/firmware/hailo/hailo10h && mkdir -p /lib/firmware/hailo/hailo10h
tar xzf "$W/fw/hailo10h_fw.tar.gz" -C /lib/firmware/hailo/hailo10h || fail "firmware unpack"

step "driver hailo1x_pci $V through DKMS (rebuilt when the kernel changes)"
D=/usr/src/hailo1x_pci-$V; rm -rf "$D"; mkdir -p "$D"
cp -a "$W/src/hailort-drivers/"{Kbuild,Makefile,common,linux} "$D/"
( cd "$D" && make -s clean >/dev/null 2>&1 || true )
sed "s/@PCIE_DRIVER_VERSION@/$V/" "$D/linux/pcie/dkms.conf.in" > "$D/dkms.conf"
dkms status "hailo1x_pci/$V" 2>/dev/null | grep -q . && dkms remove "hailo1x_pci/$V" --all
dkms add "hailo1x_pci/$V" && dkms build "hailo1x_pci/$V" -k "$KV" && dkms install "hailo1x_pci/$V" -k "$KV" || fail "dkms"
install -m 644 "$W/src/hailort-drivers/linux/pcie/hailo1x_pci.conf" /etc/modprobe.d/hailo1x_pci.conf
printf 'SUBSYSTEM=="hailo1x", MODE="0666"\n' > /lib/udev/rules.d/51-hailo-pcie-udev.rules

step "hold the kernel, so an update cannot leave the driver behind"
HOLD=$(dpkg-query -W -f='${Package} ${Status}\n' 'linux-image-*' 'linux-headers-*' 2>/dev/null | awk '/install ok installed/ {print $1}')
[ -n "$HOLD" ] && apt-mark hold $HOLD | sed 's/^/  /'
echo "  (to update the kernel later: apt-mark unhold, upgrade, then run this tool again)"

step "done: restart the unit (sudo reboot), then: sudo bash tools/hailo/check.sh"
