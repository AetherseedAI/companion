# Changelog

## 25 Nov 2026
- **Claude's own sizes.** A turn Claude answers is no longer cut to what the
  chip can hold: more memory, more of the conversation as it was said, more of
  a file, a longer answer and a longer wait (`logic/cloud.py`, `LIMITS`; the
  owner's own numbers in `cloud.json` under `limits`). The local model's sizes
  are untouched, and a turn Claude does not answer is fitted to the chip as
  before.
- **COG panel:** the essays of every model a unit has run on, to compare.

## 22 Nov 2026
- **Licence:** PolyForm Strict 1.0.0 in place of the AGPL placeholder: free
  non-commercial use; changes, redistribution and commercial use by written
  consent from Aetherseed AS. `NOTICE.md` explains it in plain words and lists
  the third-party parts. Earlier versions keep the licence they were
  published under.

## 21 Nov 2026
- **A new unit from nothing.** `tools/hailo/` builds HailoRT 5.5.0, Hailo's
  Ollama server and the driver from Hailo's public sources, fetches the
  firmware, the Qwen3-4B model and Qwen's tokenizer (each checked), installs
  them over whatever Hailo software a card has, with a way back, and holds the
  kernel. `install.sh` gains `--firewall` (checked, then applied and enabled)
  and `--first-start`, and frees the screen from a desktop login with `--kiosk`.
- **First start from a phone.** An armed unit offers the visible Wi-Fi
  "AetherSeed", its key shown as a QR code on the unit's own screen; the first
  start ends with the owner's choice of the unit's own Wi-Fi: hidden, visible,
  or none.
- **Writing.** A Write button beside the text box: longer answers in
  paragraphs, marked as a draft to check.
- **Claude and the vault.** With the owner's own Anthropic API key, Claude
  answers as the companion, with the unit's chip as the fallback. Messages
  marked Vault stay at home and are never sent. The key is set only at the
  unit's screen or from its own Wi-Fi.
- **The clock** is set from the internet when the unit has a connection; the
  firewall lets only the clock service out for it.
- **Library:** Norwegian collections are no longer dropped as "another
  language".
- The README, the install guide (with an update section) and the built-in
  manual rewritten; the user manual in English and Norwegian.

## Unreleased (unit-field, 16 Nov 2026)
- A home Wi-Fi from the console (page "Wi-Fi"): from the unit's own screen, a
  phone on its hidden network, or the steward. Root's side (tools/wifi.py)
  saves it as one NetworkManager profile (aetherseed-home, root, 600; the
  password never on a command line or in a log); tools/hotspot.sh joins it by
  the rule: a cable first, then the home Wi-Fi, then the unit's own hidden
  network, which comes back if the home Wi-Fi does not answer within 40 s and
  retries it every 5 minutes, never while a phone is on its own network.
- install.sh, on a model change: everything that asks for a model stops before
  the server restarts, and starts after it. Restarting the server during a
  load left the chip unanswering until a reboot.
- Journal memory: the latest statements older than the conversation's window
  (up to 12, questions left out) are shown every turn, so a fact told 7-20
  turns ago and asked in other words is found. Measured on a PC: recall
  in other words 31 % -> 96 %; reach ends at the window (AETHERSEED_JOURNAL_RECENT,
  default 12, chosen by the operator over 24).
- Asked about the person, after "I don't know" the answer ends (logic/decline_stop.py):
  the guess or invented quote that used to follow is never sent or stored.
- A numbered list is no longer cut after its first item; a bare "Unverified."
  opener is taken off; the tags line is found for "memories".
- The values line now reads "AetherSeed stands for and exists for ..."
  (the operator, 16 Nov): "What does AetherSeed stand for?" 0/3 -> 3/3.
- Off by default, an experiment: AETHERSEED_RECALL_NOTE (no measured effect).
- Seen on the Hailo chip: a short sentence said again in one answer (8 characters
  or more, "It is a tag.") now ends it, and parts joined by dashes count as
  sentences for the repeat stop. A decline that ends in a dash ends the answer
  too (the decline stop waited for a full stop and a tic came after).

## Current

- First start (units made from a source card) also makes the unit's admin
  account - a login name and password the owner chooses, in the sudo group,
  for updates in the field - and names the unit on the local network after
  the companion (`<name>.local:2077`, avahi). The unit's own Wi-Fi is hidden:
  joining needs its name and its passkey. The firewall admits the console
  and mDNS from the private address ranges. The admin may use SSH with its
  password (that account only, sshd drop-in checked with sshd -t), and
  `tools/lock_default.sh`, run by that admin through sudo, locks the image's
  `pi` account. The first-start screen has a button for the same: the
  admin's password is checked by root as a sign-in would check it (su as an
  unprivileged user, through PAM), then pi is locked; five wrong tries an
  hour, never logged.
- Root's answers to the console (first start, model switch, lock pi) are
  made in /run and renamed into the console's folder, and its requests are
  opened without following links: a link left there by the console can no
  longer make root write over another file.
- The console page kept its first-start step from opening on a fresh unit
  (clearing the talk removed the intro note the language switch needs), and
  the first-start screen could not be scrolled to its button on an 800 px
  screen; both fixed.
- The installer restarts the model server, the keep-alive and the proxies
  when it changes the model (the keep-alive kept asking for the old one).

- The living journal (off by default; `"memory": "journal"` in her
  config.json). Her memory of people becomes `journal.md`: one line per thing
  said to her - who, when, the words, what she did - and never her answer, so
  an old answer cannot come back to be copied. Only people she lives with
  write entries; the reader and the trainer write none. Every 12th entry
  closes a ring entry and every 20th ring entry a full ring (`rings.md`),
  made by code from the entries' own words. Both files are only ever added
  to. Turns are still stored, as the record. `/aetherseed/journal` shows both
  files, read-only.

- Files of her own, from the writer level: "save it as story.md", "write a
  poem about rain and save it as rain.md" (she writes, the unit saves),
  "put it in the writer folder", "append it to story.md", "make a folder
  called stories", "move story.md to stories", "delete the file old.md" (to
  the .trash folder, never removed). Text only (.md, .txt); .docx or PDF is
  saved as .md and she says so. A new file never replaces one; the level
  folders and the workspace's edges hold as for every tool. Each is done by
  the unit and said by the unit: "Saved: <path> (<n> bytes)".
- Fixed: asked for a story saved as a .docx, she said she could make .docx,
  said "Done!", gave a path and said she had moved the file; nothing had been
  written. "What files can you make?" is now answered by the unit; the
  follow-ups ("let me know when it's done", "where did you save it?", "put
  it in ...") get the line that nothing was done; and an answer that claims
  a file was saved, made or moved when no tool ran is followed by the unit's
  line saying nothing was saved, and kept out of memory.

- The conversation in progress is kept on the unit while you talk, in RAM:
  a page refresh draws it again, with your own words, and a restart of the
  proxy (a model switch, an install) no longer ends it. A reboot does, and it
  is never written to the card. Each person's is kept in a folder of
  `/run/aetherseed-session` that only their own proxy can see. Up to 40
  exchanges with no pause longer than two hours; with a model that has room
  (qwen3:4b) six of them go into each prompt instead of three.
- Fixed: the talk on the screen stayed when someone signed out or switched
  person, so the next person on that device could read it. It is now cleared
  when the person changes.
- The served model can be switched. The owner picks it under This unit, or at
  a shell with `sudo tools/model.py set NAME` (`tools/model.py list` shows
  what the unit can serve). The console only asks: it leaves the model's name
  for a root-side unit, which checks it against this build's models with a
  measured ceiling, a file in the model store and a tokenizer on the unit,
  writes `/etc/aetherseed/model.env` and restarts every person's proxy. If the
  proxy does not come up with the new model, the old one is put back. The
  model is the unit's, so it is the same for everyone on it.
- HailoRT 5.5.0 is accepted beside 5.4.0, and `qwen3:4b` (Hailo's
  Qwen3-4B-Instruct-2507, for a Hailo-10H with 8 GB) has a profile: 2048
  tokens of prompt. Hailo's 5.5.0 file of `qwen3:1.7b` is another compile than
  the 5.4.0 one and reads less: 1056 tokens against 1536. The unit's own file
  decides which ceiling is served.
- Fixed: a document put on the shelf could be marked ready a moment before
  the library held it, and a look-up in that moment found nothing.
- A new console page: a side menu (Talk, Memory, Library, My shelf, Notes and
  to-do, Trust and record; People and This unit for the owner only; Help), a
  header with Back, the path line, a light and dark button and the person
  using it; "who is here" and the first sign-in for each person; her
  seedling beside the talk, showing what she is doing.
- No guest. To talk with her from a phone or laptop you sign in; a device that
  has not signed in is shown who is here and the manual, cannot talk with her
  (`401`, code `sign_in`) and reads nothing of anyone's. The unit's own screen
  is still the owner's.
- More than one person on a unit, each with a root of their own: memory,
  facts, rings, shelf, notes, record and trust standing. The owner adds a
  name (`sudo tools/people.py add NAME`); that person's first sign-in chooses
  their passkey. Each root is served by a program of its own that the system
  keeps out of every other root. People, power-off and training stay the
  owner's; the owner's brake stops every root.
- The steward's own shelf: text files, a ChatGPT export and a Claude export,
  looked up when asked ("look up ... in my documents"), never memory, never
  shown to anyone else (`tools/ingest_chatgpt.py`, `tools/ingest_claude.py`).
- "Remember that" keeps a passage just shown as a steward fact, word for word
  with its source; "forget that" right after undoes it. What was kept is said
  back by the unit itself, and "Did you say that?" about a shown passage is
  answered with who wrote it.
- Look-ups, "more" and "forget that" in Norwegian; library words keep æ, ø, å
  and every other letter.
- A general collection such as Wikipedia answers unasked only by an article's
  exact title.
- Memory by meaning is on when the embedding model is installed; the
  companion's own ring sentences are no longer shown to it.
- A question about a past talk its memory knows nothing of gets a line saying
  so; an opener that only praises the question is left out.
- Its tools as MCP-shaped definitions (`tools/tool_manifest.py`); a one-file
  export of its memory (`tools/export.py`).
- Installer: the console's power-off works after a plain install (the
  shutdown path unit is installed and enabled).
- Comments and tests name no real people, units or places.
- Steward file (`steward.md` in the workspace): the steward's preferences and
  facts about themselves, kept in their own words when they ask, read out on
  request, sent with the steward's turns only.
- Shorter charter identity line; the unit itself answers "Do you know who I am?"
  for the steward and whether it is online or in a cloud.
- `install.sh --model`: qwen3:1.7b or qwen2.5:1.5b; a device keeps its model.

- Runs on HailoRT 5.4.0 with `qwen3:1.7b` on Raspberry Pi 5 + Hailo-10H.
- Memory: episodes, rings, facts and steward notes in SQLite; working memory
  carries the last exchange into the next turn.
- Trust levels (observer, writer, builder, autonomous) gate tools and
  workspace folders; higher levels reach lower folders.
- Steward and guests: guests cannot read or change the steward's data.
- Forgetting: "forget that", by topic, or everything; recorded in a chained
  log of ids and hashes only.
- Workspace: to-do list, notes and a steward-only editor.
- Tamper-evident logs, verified by `tools/verify_chain.py`.
- Training: optional loop that checks answers against a key, and keeps a
  restated lesson only if it passes.
- Installer: `install.sh`, with prerequisite checks.
