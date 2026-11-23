<p align="center">
  <img src="docs/assets/aetherseed-mark.svg" width="96" alt="Aetherseed">
</p>

<h1 align="center">AetherSeed Companion</h1>

<p align="center">
  A personal AI companion that lives on a small device in your home.<br>
  It runs on its own chip, keeps its memory with you, and says "I don't know" when it doesn't.
</p>

<p align="center">
  <a href="docs/INSTALL.md">Install</a> ·
  <a href="docs/INSTALL.md#update-a-unit-that-already-runs">Update</a> ·
  <a href="docs/manual/">User manual</a> ·
  <a href="CHANGELOG.md">Changes</a>
</p>

> **A work in progress.** The Companion is young and still changing week by
> week: some parts are rough, some will move, and some will not work the way you
> expect yet. We would love to hear what you find, what breaks, what is unclear
> and what you wish it did. Open an
> [issue](https://github.com/AetherseedAI/companion/issues), start a
> [discussion](https://github.com/AetherseedAI/companion/discussions), or write to
> contact@aetherseed.ai.

---

## What it is

The Companion is a Raspberry Pi 5 with a Hailo-10H AI chip, a screen, and this
software. You give it a name the first time it starts, and from then on it is
yours: it remembers what you tell it, looks things up in its own library, keeps
notes and files in its workspace, and grows into more tools as it earns your
trust.

| | |
|---|---|
| **Runs on the device** | The language model (Qwen3, 4 billion parameters) runs on the Hailo chip. It works with no internet at all. |
| **Memory you own** | What it remembers is a journal on the device that you can read, correct and tell it to forget. |
| **Honest by design** | Every answer says where it came from: its memory, the library, the device itself, or its own words. Library passages are shown word for word, never retold. |
| **Trust is earned** | Four levels (observer, writer, builder, autonomous) decide which tools it may use. It starts at the bottom. |
| **People, not guests** | The owner, and anyone the owner adds, sign in with their own passkey. A phone that has not signed in cannot talk with it. |
| **Claude, if you want it** | With your own Anthropic API key, Claude can answer as your companion. Anything you mark *Vault* stays at home and is never sent. Off until you switch it on. |

## Get started

**A new unit.** A Raspberry Pi 5 with a Hailo-10H (8 GB) and Raspberry Pi OS 64-bit.
The [install guide](docs/INSTALL.md) takes you from a fresh card to the first
start, in four steps and about an hour, most of it waiting for a build.

```bash
git clone https://github.com/kommandantvold-ops/aetherseed-local.git
cd aetherseed-local
sudo bash tools/hailo/build.sh        # HailoRT 5.5.0 and the model, from Hailo's sources
sudo bash tools/hailo/install.sh      # then: sudo reboot
sudo bash tools/hailo/check.sh
sudo ./install.sh --lan --kiosk --model qwen3:4b --first-start
```

The unit then shows a Wi-Fi network called **AetherSeed** and a QR code on its
screen. Scan it with your phone and do the first start there.

**A unit that already runs.** Pull and run the installer again; the memory is not
touched. See [Update a unit](docs/INSTALL.md#update-a-unit-that-already-runs).

**Using it.** The [user manual](docs/manual/) (English and Norwegian) covers
everything from the first start to the vault. The same manual is on the
console under *Help*, and the companion can look things up in it.

## Privacy, in one paragraph

Everything runs on the device: the model, the memory, the library, the logs.
The firewall lets nothing out except the clock asking the internet for the time
and, only if you switch Claude on, the companion talking to Anthropic with your
key. What you mark *Vault* is never part of that. The console is reached from the
unit's own screen, its own Wi-Fi, or your home network, and every phone or laptop
signs in first.

## For developers

```bash
python3 -m unittest discover -p "test_*.py"      # no Hailo hardware needed
```

| Path | Contents |
|---|---|
| `proxy.py` | The companion's server: memory, trust, the safety gate, model calls |
| `aetherroot.py`, `aetherspark.py` | The memory store and the safety gate |
| `logic/` | Trust, journal, workspace, library, Claude and the vault, training |
| `gui/` | The console, its sign-in, and the built-in manual |
| `tools/` | The installer's helpers, Wi-Fi, first start, and `tools/hailo/` |
| `services/` | systemd units and the firewall |
| `knowledge/`, `library/` | What the companion knows about itself, and its library tools |
| `docs/` | Install guide, glossary, user manual |

## Licence

Source-available under the [PolyForm Strict License 1.0.0](LICENSE):
free to install and use for any non-commercial purpose; not to be changed,
redistributed or used commercially without written consent from Aetherseed AS.
In plain words, with the third-party parts: [`NOTICE.md`](NOTICE.md).
Commercial use, partnerships and permissions: contact@aetherseed.ai
