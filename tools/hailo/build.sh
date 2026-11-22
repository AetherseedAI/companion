#!/bin/bash
# Build HailoRT 5.5.0, Hailo's Ollama server and the hailo1x_pci driver from
# Hailo's public sources, and fetch the firmware and the model files from
# Hailo's servers. Everything goes into one folder; nothing is installed into
# the running system except the build tools (apt). tools/hailo/install.sh
# puts the result in place.
#
#   sudo bash tools/hailo/build.sh [FOLDER]        default /var/tmp/hailort-5.5.0
#   AETHERSEED_HAILO_17B=1 ... also fetches the 5.5.0 build of Qwen3-1.7B
#
# Needs a network (GitHub, Debian, Hailo) and about 15 GB free. On a Pi 5 it
# takes 30-60 minutes. The driver is built for the kernel that is running:
# hold the kernel afterwards (apt-mark hold) so an update cannot break it.
#
# Sources, all at tag v5.5.0: github.com/hailo-ai/hailort, hailort-drivers,
# hailo_model_zoo_genai. Firmware: Hailo's S3. Model files: dev-public.hailo.ai.
# The Qwen3-4B model needs a Hailo-10H with 8 GB of memory.
set -u
W=${1:-/var/tmp/hailort-5.5.0}; S=$W/src; ST=$W/stage; V=5.5.0; J=$(nproc)
step() { echo "== $(date '+%F %T') $*"; }
fail() { step "STOPPED: $*"; exit 1; }
[ "$(id -u)" = 0 ] || fail "run as root (sudo)"
mkdir -p "$W" "$S" "$W/fw" "$W/model"

step "network check"
getent hosts github.com >/dev/null || fail "no name lookup: this unit needs a network for the build"

step "build tools (apt)"
apt-get update -qq || fail "apt update"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential cmake cargo rustc libssl-dev git pkg-config dkms curl >/dev/null || fail "apt install"
[ -d "/lib/modules/$(uname -r)/build" ] || fail "no kernel headers for $(uname -r): install linux-headers-rpi-2712 (or your kernel's headers) first"

step "sources at v$V"
for r in hailort hailort-drivers hailo_model_zoo_genai; do
  [ -d "$S/$r" ] || git clone -q --depth 1 -b "v$V" "https://github.com/hailo-ai/$r" "$S/$r" || fail "clone $r"
  echo "  $r $(git -C "$S/$r" rev-parse --short HEAD)"
done

fetch() { # fetch <url> <file> <size>
  [ "$(stat -c %s "$2" 2>/dev/null)" = "$3" ] && return 0
  curl -fsSL -C - -o "$2" "$1" || return 1
  [ "$(stat -c %s "$2")" = "$3" ]
}
step "firmware and model files"
fetch "https://hailo-hailort.s3.eu-west-2.amazonaws.com/Hailo10H/$V/FW/hailo10h_fw.tar.gz" "$W/fw/hailo10h_fw.tar.gz" 37899283 || fail "firmware"
fetch "https://dev-public.hailo.ai/v$V/blob/Qwen3-4B-Instruct-2507.hef" "$W/model/Qwen3-4B-Instruct-2507.hef" 5656354387 || fail "Qwen3-4B model file"
if [ "${AETHERSEED_HAILO_17B:-0}" = 1 ]; then
  fetch "https://dev-public.hailo.ai/v$V/blob/Qwen3-1.7B-Instruct.hef" "$W/model/Qwen3-1.7B-Instruct.hef" 2955754430 || fail "Qwen3-1.7B model file"
fi
# The companion counts prompt tokens with the Qwen3 tokenizer (one for the
# 1.7B and the 4B), published by Qwen; checked against its sha256.
fetch "https://huggingface.co/Qwen/Qwen3-1.7B/resolve/main/tokenizer.json" "$W/qwen3-1.7b.tokenizer.json" 11422654 || fail "Qwen3 tokenizer"
echo "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4  qwen3-1.7b.tokenizer.json" | ( cd "$W" && sha256sum -c --quiet ) || fail "the Qwen3 tokenizer does not match its sum"
( cd "$W" && sha256sum fw/*.tar.gz model/*.hef qwen3-1.7b.tokenizer.json | tee sha256.txt )

step "HailoRT $V (with hailortcli)"
cmake -S "$S/hailort" -B "$W/b-hailort" -DCMAKE_BUILD_TYPE=Release -DHAILO_BUILD_TOOLS=OFF \
      -DCMAKE_INSTALL_PREFIX=/usr >"$W/b-hailort.cfg.log" 2>&1 || { tail -30 "$W/b-hailort.cfg.log"; fail "configure hailort"; }
cmake --build "$W/b-hailort" -j"$J" >"$W/b-hailort.log" 2>&1 || { tail -40 "$W/b-hailort.log"; fail "build hailort"; }
DESTDIR="$ST" cmake --install "$W/b-hailort" >"$W/b-hailort.inst.log" 2>&1 || fail "stage hailort"

step "Hailo's Ollama server"
cmake -S "$S/hailo_model_zoo_genai" -B "$W/b-genai" -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_PREFIX_PATH="$ST/usr" -DCMAKE_INSTALL_PREFIX=/usr >"$W/b-genai.cfg.log" 2>&1 || { tail -30 "$W/b-genai.cfg.log"; fail "configure genai"; }
cmake --build "$W/b-genai" -j"$J" >"$W/b-genai.log" 2>&1 || { tail -40 "$W/b-genai.log"; fail "build genai"; }
DESTDIR="$ST" cmake --install "$W/b-genai" >"$W/b-genai.inst.log" 2>&1 || fail "stage genai"

step "driver hailo1x_pci $V (checked against the running kernel; installed later through DKMS)"
make -C "$S/hailort-drivers" all >"$W/b-driver.log" 2>&1 || make -C "$S/hailort-drivers" pcie >>"$W/b-driver.log" 2>&1 \
  || { tail -30 "$W/b-driver.log"; fail "build driver"; }

ls -l "$ST"/usr/bin/hailo-ollama "$ST"/usr/bin/hailortcli "$ST"/usr/lib/*/libhailort.so."$V" 2>/dev/null
step "done: everything is in $W. Next: sudo bash tools/hailo/install.sh $W"
