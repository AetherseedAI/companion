# Install the AetherSeed Companion

From a fresh SD card to a companion with a name: four steps, about an hour.
Most of that hour is the HailoRT build, which runs on its own.

- [What you need](#what-you-need)
- [Step 1 — Prepare the card](#step-1--prepare-the-card)
- [Step 2 — HailoRT 5.5.0 and the model](#step-2--hailort-550-and-the-model)
- [Step 3 — The Companion](#step-3--the-companion)
- [Step 4 — The first start](#step-4--the-first-start)
- [Update a unit that already runs](#update-a-unit-that-already-runs)
- [After the first start](#after-the-first-start)
- [Network and access](#network-and-access)
- [If something is wrong](#if-something-is-wrong)
- [Tests, where things are, uninstall](#tests)

## What you need

| | |
|---|---|
| Board | Raspberry Pi 5 (8 GB or 16 GB) |
| AI chip | Hailo-10H with **8 GB** of memory (for example the Raspberry Pi AI HAT+ 2). The 4B model does not fit the 4 GB version. |
| Card | 64 GB or more (the model files alone are about 9 GB) |
| System | Raspberry Pi OS 64-bit, Debian 13 "Trixie", **with desktop** (it brings the screen's browser) |
| Screen | Any HDMI screen; a touch screen works too |
| Network | A cable or Wi-Fi for the install. Afterwards the unit runs without internet. |

## Step 1 — Prepare the card

1. In **Raspberry Pi Imager**, choose *Raspberry Pi OS (64-bit)* and open the
   settings before writing: set a **hostname**, a **user and password**, your
   **Wi-Fi** if you have no cable, and switch **SSH** on.
2. Start the Pi with the card, wait for the desktop, and open a terminal
   (or connect with `ssh <user>@<hostname>.local`).
3. Bring the system up to date once, and fetch this repository:

   ```bash
   sudo apt update && sudo apt full-upgrade -y && sudo reboot
   git clone https://github.com/kommandantvold-ops/aetherseed-local.git
   cd aetherseed-local
   ```

   Do the full upgrade now, before Step 2: the chip's driver is built for the
   kernel that is running, and Step 2 holds that kernel afterwards.

## Step 2 — HailoRT 5.5.0 and the model

The Companion talks to the Hailo chip through HailoRT 5.5.0. Hailo publishes
its source, not packages, so the unit builds it once. Three commands:

```bash
sudo bash tools/hailo/build.sh       # 30-60 minutes; needs about 15 GB free
sudo bash tools/hailo/install.sh
sudo reboot
```

After the restart:

```bash
cd aetherseed-local
sudo bash tools/hailo/check.sh       # "ready" when the chip runs 5.5.0
```

What they do, so you know what is on your unit:

- **build.sh** fetches Hailo's sources at tag `v5.5.0` (`hailort`,
  `hailort-drivers`, `hailo_model_zoo_genai`) from GitHub, the chip's firmware
  and the Qwen3-4B model from Hailo's servers, and Qwen's tokenizer from Hugging
  Face. Each download is checked by its size or its checksum. It builds into
  `/var/tmp/hailort-5.5.0` and installs nothing but the build tools.
- **install.sh** replaces whatever Hailo software the card had (none, or an
  older version) with the 5.5.0 build, registers the driver with DKMS, and
  holds the kernel so an update cannot leave the driver behind. It keeps what
  it replaced in `/var/tmp/hailort-5.5.0/before/` — the way back is written at
  the top of the script.
- **check.sh** confirms the driver, the device and the firmware after the
  restart.

## Step 3 — The Companion

```bash
sudo ./install.sh --lan --kiosk --model qwen3:4b --firewall --first-start
```

| Option | What it does |
|---|---|
| `--lan` | The console can be reached from your home network, not only from the unit's own screen. |
| `--kiosk` | The unit's screen shows the companion, full screen. The desktop's login screen is switched off for this. |
| `--model qwen3:4b` | The model the companion thinks with. `qwen3:1.7b` is smaller and faster, if you built it too. |
| `--firewall` | Puts the unit's firewall in place (see [Network and access](#network-and-access)). |
| `--first-start` | Makes the unit wait for its first start and offer the setup Wi-Fi. Only on a unit nobody has set up. |
| `--check` | Lists what is missing and changes nothing. |

The installer runs the companion as its own account, `aetherseed`, puts the
program in `/opt/aetherseed` and the memory in `/var/lib/aetherseed`, and
starts everything. It is safe to run again. Restart the unit once when it
asks you to, so the screen comes up on the companion.

## Step 4 — The first start

The screen now shows a QR code and a Wi-Fi network called **AetherSeed**.
Do the first start from your phone, or at the unit's own screen:

1. **Join AetherSeed** — scan the code with the phone's camera, or type the
   key shown under it. Then open `http://10.42.0.1:2077`.
2. **Choose the language** and **give your companion a name**. You may add
   your own name, so it knows who its steward is.
3. **The date and time**, if the unit has no internet yet.
4. **Two passkeys**, 8 to 63 characters each, written down before you go on:
   one for the companion's own Wi-Fi, and your own steward passkey for
   signing in.
5. **An admin account** for updates in the field: a login name and a password
   of 12 or more characters.
6. **Its own Wi-Fi from now on:** hidden (the safest), visible, or none
   (reached only through your home network, which needs a cable or a home
   Wi-Fi).

Press **Start**. The setup network goes away and the unit is yours. The user
manual (in [`docs/manual/`](manual/) and on the console under *Help*) takes
it from here.

## Update a unit that already runs

Your companion's memory, people and settings are not touched by an update.

```bash
cd aetherseed-local
sudo systemctl stop nftables         # opens the firewall for the update (if it has one)
git pull
hailortcli --version                 # 5.5.0? then skip the next line
#   older: run Step 2 first (build.sh, install.sh, reboot, check.sh)
sudo ./install.sh --lan --kiosk --firewall      # --firewall closes it again
```

Leave out `--first-start` on a unit in use. If the unit runs `qwen3:1.7b` and
should move to the 4B, add `--model qwen3:4b` (the owner can also switch it
later, under *This unit*). The installer does not run the tests; to run them
on the unit first, see [Tests](#tests).

## After the first start

Everything here is in the user manual too; these are the shell versions.

**People.** The owner adds people at the console (*People*), or:

```bash
sudo /opt/aetherseed/tools/people.py add NAME
sudo /opt/aetherseed/tools/people.py reset NAME     # their next sign-in chooses a new passkey
sudo /opt/aetherseed/tools/people.py remove NAME    # their memory is moved aside, not deleted
```

**The model.** The owner switches it under *This unit*, or:

```bash
/opt/aetherseed/tools/model.py list
sudo /opt/aetherseed/tools/model.py set qwen3:4b
```

**Claude.** On the unit page, the owner puts in their own Anthropic API key
(at the unit's screen or from its own Wi-Fi only, never over the home network)
and switches Claude on. The owner pays Anthropic for what is used. Messages
marked *Vault* stay at home. See the user manual, chapter *Claude and the vault*.

**Your documents and chat history.** PDFs and text files go on *My shelf* at
the console. A ChatGPT or Claude data export comes in from the shell:

```bash
sudo -u aetherseed HOME=/var/lib/aetherseed /opt/aetherseed/venv/bin/python3 \
    /opt/aetherseed/tools/ingest_chatgpt.py preview export.zip   # or ingest_claude.py; then add
```

**Memory by meaning (optional).** With the small embedding model
all-MiniLM-L6-v2 (Apache-2.0, about 90 MB) in `/var/lib/aetherseed/embed/`
(`model.safetensors` and `tokenizer.json`, owned by `aetherseed`), the
companion also finds earlier talk by what it was about, not only its words.
Index what is stored, with the companion stopped:

```bash
sudo systemctl stop aetherseed-proxy
sudo -u aetherseed HOME=/var/lib/aetherseed /opt/aetherseed/venv/bin/python3 \
    /opt/aetherseed/tools/semantic_index.py --build
sudo systemctl start aetherseed-proxy
```

## Network and access

**How the unit finds a network:** a cable first, then a home Wi-Fi you have
given it (at the console, *Wi-Fi*), then its own Wi-Fi. If the home Wi-Fi
stops answering, its own network comes back within a minute, so it can always
be reached. On your home network the console is at `http://<name>.local:2077`.

**The firewall** (`services/nftables.conf`, put in place by `--firewall`):

- **In:** the console and SSH from private home-network addresses, the
  console from the unit's own Wi-Fi, and its name on the network (mDNS).
- **Out:** nothing the unit starts, except the clock asking the internet for
  the time, and — only while the owner has Claude switched on — the
  companion's own process talking to Anthropic. Nothing else on the unit, not
  even the screen's browser, gets out.

With the firewall in place nothing else gets out — not `git pull`, not
`apt`, not the HailoRT build. For an update, open it with
`sudo systemctl stop nftables` and close it again with the installer's
`--firewall`, as [Update](#update-a-unit-that-already-runs) shows. To change
the rules: edit `services/nftables.conf`, check it with
`sudo nft -c -f services/nftables.conf`, and run the installer with
`--firewall` again.

**SSH.** The admin account made at the first start can sign in over SSH with
its password. If the card has an account called `pi`, the unit's screen
offers after the first start to lock it, so the admin is the only way in (way
back: `sudo usermod -U -e "" pi`). An account with another name is left as it
is. For SSH by key only, put your public key in
`~/.ssh/authorized_keys` and switch passwords off in
`/etc/ssh/sshd_config.d/`.

## If something is wrong

| What you see | What to do |
|---|---|
| The screen stays on the desktop or is blank | Restart once after Step 3. If it persists: `systemctl status aetherseed-kiosk`. |
| `install.sh` says a prerequisite is missing | It names it. Most often: Step 2 was not finished (`tools/hailo/check.sh`). |
| `hailo-ollama` does not start | `journalctl -u hailo-ollama -n 30`. The chip must show as `/dev/h1x-0`; run `tools/hailo/check.sh`. |
| The clock is wrong | It corrects itself once the unit is online, with the firewall from `--firewall`. Until then, set it at the first start. |
| No AetherSeed network appears | The unit needs working Wi-Fi. `sudo bash /opt/aetherseed/tools/hotspot.sh status`. |
| `<name>.local` does not open | Use the unit's address instead; some routers and Windows PCs do not resolve `.local` names. |

## Tests

```bash
python3 -m unittest discover -p "test_*.py"
```

They need no Hailo hardware and run on any machine with Python 3.11 or newer.
On a unit, keep them away from the unit's own library and embedding model:

```bash
AETHERSEED_LIBRARY=/nonexistent AETHERSEED_EMBED_DIR=/nonexistent python3 -m unittest discover -p "test_*.py"
```

## Where things are

| | |
|---|---|
| Program | `/opt/aetherseed` |
| Memory, logs, library, workspace | `/var/lib/aetherseed` |
| People's own memories | `/var/lib/aetherseed-people` |
| Model setting | `/etc/aetherseed/model.env` |
| Services | `/etc/systemd/system/aetherseed-*`, `hailo-ollama.service` |
| HailoRT build and its way back | `/var/tmp/hailort-5.5.0` |

Check that the logs are untouched at any time:

```bash
sudo -u aetherseed /opt/aetherseed/venv/bin/python3 /opt/aetherseed/tools/verify_chain.py
```

## Uninstall

```bash
sudo systemctl disable --now aetherseed-proxy aetherseed-gui aetherseed-warmup aetherseed-keepalive \
  aetherseed-shutdown.path aetherseed-model.path aetherseed-wifi.path aetherseed-hotspot hailo-ollama \
  aetherseed-kiosk aetherseed-kiosk-watch 2>/dev/null
sudo rm -rf /opt/aetherseed /etc/systemd/system/aetherseed-* /etc/systemd/system/hailo-ollama.service* \
  /etc/udev/rules.d/99-aetherseed-hailo1x.rules /etc/aetherseed
sudo systemctl daemon-reload
# The memory stays in /var/lib/aetherseed. Delete it only if you want it gone.
# The desktop login comes back with: sudo systemctl enable lightdm && sudo systemctl set-default graphical.target
```
