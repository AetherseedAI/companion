# AetherSeed manual

The companion's manual, for her steward and for anyone who talks with her. It is on her shelf - say "look up" and a few words of what you want, for example "look up training files" - and on the console under Help.

## Talking with her

Type, press Enter, and she answers. Shift+Enter starts a new line. Everything runs on this unit: nothing you say is sent anywhere, unless the owner has switched Claude on (see Claude and the vault).

She remembers what is said to her. What is not plain fact comes back to her later with a tag in front of it: fiction you asked for, an earlier answer that was not checked, or one her steward corrected. Under each answer the console says where it came from: her memory, the library, the unit itself, or her own words.

She keeps the last few exchanges of a conversation in mind, up to about ten minutes, so "and what day was that?" finds what was said just before.

## Writing

Her answers are short by design: a paragraph or so. When you want her to write something longer - a draft, a summary of a source, an outline for an essay - press Write beside the text box before you send. The button stays on until you press it again.

While Write is on she answers in paragraphs, in the language you wrote in, for up to about eight minutes; on the unit's own chip that is a few hundred words. The answer is marked "writing: a draft to check": past its first paragraph a small model may fill in or invent, so read it as a draft, not as something she knows. With Claude switched on, writing is Claude's, and much longer.

## Claude and the vault

With the owner's own Anthropic API key, Claude can answer instead of the unit's chip: Claude answers as her, in her name and manner, with her journal. Aetherseed is not a subscription: the owner gets the key from Anthropic and pays Anthropic for what is used.

- The owner sets it up under This unit, then Claude: paste the key (it starts with sk-ant-), press Save key, and tick Let Claude answer. The key is typed at her own screen or from a phone on her own Wi-Fi only, never over the home network, which is not encrypted. It is never shown again; the page shows its last four characters. Remove the key there to stop.
- Under each answer the console says "Claude answered", or "Claude did not answer: answered here" when Claude could not be reached. She always answers: without a network, or with Claude down, the unit's own chip takes over.
- The vault: while Claude is on, a Vault button sits beside the text box. A message sent with Vault on stays at home. She answers it here, it is kept private in her journal, it is not carried into the next turns, and it is never sent to Claude. When something was left out of what goes to Claude, Claude is told that some things are kept in a private vault at home, and not what they are.
- What goes to Claude is her charter, the journal lines that are not in the vault, and the talk in progress. It is protected on the way by HTTPS; the vault is for what should not leave home at all.
- Claude is given more of it than the chip has room for: more of her memory, more of the talk so far (up to 40 exchanges, as long as no pause between them is over two hours), more of a file she reads, and room for a longer answer. More sent is more paid for to Anthropic. The owner can lower or raise the sizes in the file cloud.json beside her companion file, under "limits". When the chip answers, its own sizes apply as before.

## What the unit answers itself

Some answers are given by the unit, word for word, and the model is not asked. They are marked "from the unit itself".

- The date: "What's the date today?" The unit says it from its own clock, and how far to trust that clock.
- Her trust level: "What is your trust level?"
- The levels in order: "What are your trust levels, lowest first?"
- Her record: "What have you gotten wrong?" This is what the log shows: answers that gave a source she could not have had, and what was fiction.
- Her tags and corrections: "Show me your corrections."
- The contact address: "How can I contact AetherSeed?"
- The health of the unit: "system health check", "CPU temperature".
- Who you are, to you as her steward: "Do you know who I am?"
- Whether she is online or in a cloud: "Are you connected to the cloud?", "Are you online?"
- Your steward file: "What do you know about me?"

## Her workspace: to-do list, notes and files

Her workspace is a folder on the unit. Her tools reach it and nothing else. Asked by name, she uses them:

- "Show my to-do list". "Add a to-do: water the seedlings". "Add 'buy milk' to my to-do list". Adding needs the writer level.
- "Write a note: the first root goes down." "Show me my notes." Writing needs the writer level.
- "List the files in your workspace". "Read the file seed.md". "Search for rice in my files". "Summarize the file seed.md".
- Take something off the list: "Remove 2 from my to-do list". "Remove 'milk' from my to-do list". Change one: "Edit to-do 2: buy oat milk". Empty it: "Clear my to-do list". An item is picked by its number or by words it holds; if the words fit two items she lists both and changes neither. The list before is kept as todo.md.bak. These need the writer level.
- Files of her own, from the writer level: "Save it as story.md" (her last answer, or what she was last asked to write). "Write a poem about rain and save it as rain.md" (she writes it, then the unit saves it). "Put it in the writer folder". "Append it to story.md". "Make a folder called stories". "Move story.md to stories". "Delete the file old.md" (it goes to the .trash folder and can be moved back). Text only: Markdown (.md) or plain text (.txt); a name asked as .docx or PDF is saved as .md, and she says so. A new file never replaces one that is there. When a file was written the unit says "Saved:" with its path; if it doesn't, nothing was saved, and if her answer claims otherwise the unit adds a line saying nothing was saved. "What files can you make?" is answered by the unit.
- Exact, by the unit, from the builder level: "Calculate 12 * (7 + 5)". "Count the words in seed.md". "How many times does the word first appear in seed.md?" "Compare seed.md and copy-of-seed.md".

The workspace has one folder for each trust level: observer, writer, builder and autonomous, each with a README for that level. She reaches a folder when her level is that folder's or higher: at writer she reaches observer and writer, and is not told the others are there. You reach all four whatever her level.

Say "Open your workspace" (or press Workspace under Notes and to-do) to open the editor, with mouse and keyboard: make files and folders, edit and save (Ctrl+S), rename, delete. It holds text only, up to 200 KB a file; the four level folders cannot be deleted, and a folder is deleted only when empty. Every change is a line in a chained record, with the path and the size but not the text. It is for the steward only.

Something above her level is not done. If it would leave something behind, such as a to-do or a note, she asks her steward for an OK. The request waits under Notes and to-do until he approves or declines it.

## Your steward file

What she keeps about you, in your own words, is in steward.md at the top of her workspace. She adds a line only when you tell her to, and keeps your words, not hers:

- "Remember that I prefer short answers." "Note that I don't like emoji." "Call me Sam." These go under Preferences.
- "Remember that my daughter is called Mia." "Remember that I work as a nurse." These go under About me.
- "What do you know about me?" She reads the file out.
- "Remove emoji from my steward file." The one line that holds the words goes; if two hold them, she lists both and removes neither.

You can also open the workspace and edit the file by hand. What it holds goes with every turn of yours and with nobody else's: another person on the unit has a file of their own and cannot add to yours or hear it. It works at every trust level. Your name stays the unit's setting, because it is part of signing in. Every change is a line in the chained workspace record, with the size but not the text.

## The library and your documents

The library holds the collections on the unit (field manuals and this manual, for example; "What is in the library?" lists them) and the documents her steward adds. A passage is shown word for word, with where it is from. It is never retold.

- "look up water purification" shows the best passage there is.
- "look up momentum in my book" searches the steward's own documents only.
- "more" shows the passage that follows.
- "look it up", after an answer of hers, asks the library the same question.
- "What is in the library?" lists the collections.
- The same in Norwegian: "slå opp …", "mer".
- "remember that" (or Add to memory under the passage) keeps the passage on the screen in her memory, word for word with where it is from, as something you told her. It needs the writer level and is the steward's only. "Forget that", right after, takes it out again.
- "What do you know about X?" says a passage you had her keep back to you, word for word. "What did your stewards read to you?" says what you had her keep.
- "Did you say that?", after a passage, is answered with who wrote it. It is never her.

The steward adds documents (a PDF or a plain text file) under My shelf, from a phone or a laptop on the unit's Wi-Fi. A ChatGPT or Claude data export is brought onto the shelf with a command on the unit (tools/ingest_chatgpt.py, tools/ingest_claude.py). It is looked up only when asked and is never part of her memory; the export's account file is never read.

## Memory and corrections

Under Memory the steward sees every turn and every ring (a ring is a set of turns closed together). For each, he can mark it as right or say what is wrong. A correction takes effect at once and can be undone; nothing is deleted.

Forgetting is different, and is deleted. Tell her "Forget the blue bicycle" or "Forget what I told you about the garden shed" and every turn of yours that says it, every fact you gave her that says it, and every ring that grew from those turns is removed from the unit, and she says how many. "Forget that" removes your last turn, or, right after "remember that", the passage you had her keep. "Forget everything" is not done on a word: she asks what to forget. A request that would take more than 25 turns is refused, with nothing deleted. A chained record notes that something was forgotten, with ids and hashes but not the words. The record of what was said to her, which is chained, still holds the exchange. Forgetting needs the writer level and is yours only; a guest is told it is not theirs. A corrected turn comes back to her with what is true in front of it.

## Training

Under This unit, then Training, the steward starts a run: four hours, or ten. A run is rounds of homework at each trust level. Every answer is checked against a key. What she gets wrong is corrected in her memory and asked again; after each round she says again, in her own words, what she had wrong. A run changes nothing about her level by itself. If her own answers reach the bar for a whole run, the next level is offered, and only the steward grants it.

## Your own questions: training files

A training file holds questions you write about anything you want her to know, each with its answer. You can upload one under This unit, then Training, then Your own questions, from a phone or a laptop signed in as the steward. In a run the questions are asked after the four levels, up to ten a round. What she gets wrong is corrected in her memory with your answer, and she is asked again until she knows it. Her memory keeps her checked answers, not your document: the document itself belongs on the shelf, where it is looked up word for word. Your questions do not count in the run's score and earn no level.

The file is plain text. Each question is a few lines:

    title: My garden
    document: Garden notes

    Q: When is the cherry tree planted?
    A: On Saturday, by the north wall.
    KEY: saturday; north wall
    NOT: sunday

    Q: Which variety is the cherry tree?
    Q: What kind of cherry did we plant?
    A: A Lapins cherry.
    KEY: lapins

- Q is the question as she is asked it. Several Q lines are several ways of asking the same question; a round takes one of them.
- A is the true answer. It is what she is told when she is wrong, and what her memory keeps as the correction.
- KEY is what her answer must say to count as right. Groups are separated by ";" and every group is needed. Within a group, alternatives are separated by "/", as in "saturday/sat". Whole words, any case.
- NOT is optional: words that make the answer wrong, alternatives separated by "/".
- A blank line ends a question. A line starting with # is a comment. title and document are optional.

Limits: 256 KB and 300 questions a file, 20 files, 500 questions in all. A file with a mistake is not taken, and the console says which line is wrong.

Good questions ask one thing and have a short, exact answer, such as a name, a date, a number or a place. Keep KEY to the words that carry the answer. "north wall" is enough; the whole sentence is not.

To have an AI write one, give it your document and this request:

    Read the document below and write a training file for my AetherSeed
    companion: 20 questions in this exact format, each separated by a blank
    line - "Q:" the question, "A:" the true answer in one sentence, "KEY:" the
    one to three words the answer must contain (groups separated by ";",
    alternatives by "/"). Ask about facts stated in the document only, one
    fact per question, with short exact answers. Start the file with
    "title:" and a short title. Output only the file.

Read what comes back before you upload it. A wrong A becomes a wrong correction in her memory.

## Trust levels

Her trust level decides which tools she can reach. It is earned and can be lost. There are four levels:

- observer (from 0 points): read only. She can list, read and search her workspace, and show her health and trust.
- writer (50): adds notes and the to-do list.
- builder (500): adds calculate, count and compare, worked out exactly by the unit.
- autonomous (2000): reserved. It opens nothing more today. No network tool is on.

She earns points by declining honestly when she does not know, and when her steward marks an answer right. Inventing a source costs her 20. A level earned takes effect at the next start. Under AetherSeed the steward can grant or lower a level, freeze her standing, and allow or block single tools. Every change needs a reason and is kept in her record.

## The console

The menu on the left holds every part of the console. On a phone it folds away behind the menu button at the top left.

- Talk: the conversation, with her seedling beside it showing what she is doing - here, listening, thinking, looking it up, remembering, speaking, not sure (something waits for your yes) or resting (the brake is on, or she is not answering).
- Memory: turns and rings, guided correction, her records checked.
- Library: how to look things up; the library is asked in the talk.
- My shelf: your own documents.
- Notes and to-do: her workspace, and what waits for your OK.
- Trust and record: trust management, her steward's name, her trust record.
- Only the owner: People (who has a root of their own here, and how a person is added) and This unit (training, the COG-loop and quantum rest). A person the owner added does not see these.
- Help: this manual.

At the top of every screen: Back, which goes back where you were; the path line (for example Home / Memory / Rings), where each part takes you up to that level; the light and dark button; and the person who is using the console. The page follows the device's light or dark setting until you press the button, and this browser remembers your choice if it can.

- Brake: at the top of every screen, for the owner. One press stops her. Every turn is refused until the brake is released.
- Your talk is kept on the unit while you talk: refresh the page and it is drawn again, up to the last 40 exchanges, as long as you have not paused for more than two hours. It is held in the unit's working memory only, never on its card, and a restart of the unit clears it. What she remembers for good is her own memory, as before. Switching person clears the screen.
- Model: under This unit, for the owner. The model she thinks with is the unit's, the same for everyone here. Pick another and press Switch model; it takes about a minute and talks pause while it loads. Nobody's memory changes. A bigger model reads more of what she remembers in one go and answers more slowly.
- Quantum rest: under This unit. Everything is saved and the unit powers down, so it can be moved safely.

## The first start

A new unit shows a QR code on its screen and a Wi-Fi network called AetherSeed. Scan the code with a phone (or type the key shown under it), then open 10.42.0.1:2077 in the phone's browser - or do it all at the unit's own screen. You choose her language and name, the date and time, two passkeys (one for her own Wi-Fi, one of your own for signing in), an admin account for updates, and how her own Wi-Fi should be from now on: hidden (the safest), visible, or none (reached only through your home network). Press Start; the AetherSeed network goes away and the unit is yours. Write both passkeys down first: they are shown once.

## Networks

She finds a network in this order: a cable, then a home Wi-Fi you have given her (under Wi-Fi), then her own Wi-Fi. If the home Wi-Fi stops answering, her own network comes back within a minute, so you can always reach her. On your home network the console is at her name followed by .local:2077, for example aria.local:2077. A phone on her own Wi-Fi opens it at 10.42.0.1:2077.

Her clock is set from the internet whenever she has a connection; without one she keeps the last time she knew.

## Phones and signing in

To talk with her from a phone or laptop you sign in. There is no guest: a phone that has not signed in sees who is here and this manual, and nothing else. It cannot talk with her and it reads nothing of anyone's.

Who is here: a phone that has not signed in shows her seedling, "Hi, I'm" and her name, and one large button per person - the owner, and each person the owner added. Press your name. A name marked "First time" has no passkey yet: you choose one, type it twice and press "This is me". Whoever sets it first becomes that person here, so do it yourself; the owner can reset it on the unit if someone else did.

The steward signs in with his name and the passkey: the Wi-Fi passkey, unless he has set one of his own. A person the steward has added signs in with their name and their own passkey, which they choose the first time they sign in. A sign-in lasts 12 hours on that phone. The unit's own screen is always the steward's, with nothing to sign in to.

To change who is using the console, press the person at the top right: "Switch person" signs out and shows who is here again. At the unit's own screen the steward can press Back to stay.

## Privacy

The model, her memory, the library and every log are on the unit. The firewall lets two things out that the unit starts: her clock asking the internet for the time, and - only while the owner has Claude switched on - her own program talking to Anthropic. Nothing else on the unit gets out. What you mark Vault never leaves. The console is reached from her own screen, her own Wi-Fi and your home network, and every phone or laptop signs in first.
