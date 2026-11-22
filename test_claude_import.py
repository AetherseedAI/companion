"""A Claude export onto the steward's own shelf: read, left out, looked up,
removed. The export here is made for the test; a real one is never used."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import claude_import as ci  # noqa: E402
from logic import library as L  # noqa: E402
from logic import own_shelf  # noqa: E402
from logic import remember  # noqa: E402
from tools import ingest_claude  # noqa: E402

SECRET = "owner.secret@example.org"


def export(path, extra=True):
    convs = [
        {"uuid": "c1", "name": "Attachment theory notes", "created_at": "2025-03-02T10:00:00.000Z",
         "project": {"uuid": "p1", "name": "Study notes"},
         "chat_messages": [
             {"uuid": "m1", "sender": "human", "created_at": "2025-03-02T10:00:00.000Z",
              "text": "What did Bowlby mean by a secure base?", "content": [],
              "attachments": [{"file_name": "lecture3.txt", "file_size": 40, "file_type": "text/plain",
                               "extracted_content": "Lecture 3: the strange situation procedure."}],
              "files": [{"file_name": "lecture3.txt"}, {"file_name": "diagram.png"}]},
             {"uuid": "m2", "sender": "assistant", "created_at": "2025-03-02T10:00:05.000Z", "text": "",
              "content": [{"type": "thinking", "thinking": "a hidden thought"},
                          {"type": "tool_use", "name": "web_search", "input": {}},
                          {"type": "text", "text": "A secure base is the caregiver a child explores from."}]},
         ]},
        {"uuid": "c2", "name": "", "created_at": "2025-04-01T09:00:00Z", "project_uuid": None,
         "chat_messages": [{"uuid": "m3", "sender": "human", "created_at": "2025-04-01T09:00:00Z",
                            "text": "Lag en handleliste", "content": [{"type": "text", "text": "Lag en handleliste"}]}]},
        {"uuid": "c3", "name": "Empty", "created_at": "2025-04-02T09:00:00Z", "chat_messages": []},
    ]
    projects = [{"uuid": "p1", "name": "Study notes", "created_at": "2025-02-01T08:00:00Z",
                 "description": "exam reading", "prompt_template": "Answer as a patient tutor.",
                 "docs": [{"uuid": "d1", "filename": "syllabus.md", "content": "Week 1: developmental psychology."}]}]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json", json.dumps(convs))
        z.writestr("projects.json", json.dumps(projects))
        if extra:
            z.writestr("users.json", json.dumps([{"email_address": SECRET, "full_name": "Owner"}]))
            z.writestr("memories.json", json.dumps([{"conversations_memory": SECRET}]))


class TheImport(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="claude-import-")
        self.zip = os.path.join(self.d, "export.zip")
        export(self.zip)
        self.shelf = os.path.join(self.d, "shelf")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_preview_counts_what_comes_in_and_what_is_left_out(self):
        p = ci.preview(self.zip)
        self.assertEqual((p["conversations"], p["projects"]), (2, 1))
        self.assertEqual((p["yours"], p["claude"], p["project_texts"]), (3, 1, 2))
        self.assertEqual(p["left_out"]["the assistant's thinking"], 1)
        self.assertEqual(p["left_out"]["tool calls and their results"], 1)
        self.assertEqual(p["left_out"]["uploaded files (only their names are in the export)"], 1)
        self.assertEqual(p["left_out"]["conversations with no words in them"], 1)
        self.assertEqual(p["not_read"], ["memories.json", "users.json"])
        self.assertIn("not into memory", ci.preview_text(p))
        self.assertFalse(os.path.exists(self.shelf))            # a preview writes nothing

    def test_what_comes_in_and_never_the_rest(self):
        msgs, _, _, _ = ci.messages(self.zip)
        heads = [(m["title"], m["who"]) for m in msgs]
        self.assertIn(("Study notes: Attachment theory notes", "You"), heads)
        self.assertIn(("Study notes: Attachment theory notes", "You (attached file: lecture3.txt)"), heads)
        self.assertIn(("Study notes: Attachment theory notes", "Claude"), heads)
        self.assertIn(("Project: Study notes", "Project instructions"), heads)
        self.assertIn(("Project: Study notes", "Project document: syllabus.md"), heads)
        self.assertIn(("Untitled conversation", "You"), heads)
        words = " ".join(m["text"] for m in msgs)
        self.assertNotIn("hidden thought", words)
        self.assertEqual(msgs[0]["date"], "2025-03-02")
        e = ci.bring_in(self.zip, self.shelf)
        self.assertEqual((e["state"], e["source"], e["title"]), (own_shelf.READY, "claude-export", "Claude history"))
        for root, _, files in os.walk(self.shelf):
            for f in files:
                with open(os.path.join(root, f), "rb") as fh:
                    self.assertNotIn(SECRET.encode(), fh.read(), f)

    def test_looked_up_never_unasked_said_whose_it_is(self):
        ci.bring_in(self.zip, self.shelf)
        lib = L.Library(os.path.join(self.d, "nobuiltin"), own=self.shelf)
        hit = lib.look_up("secure base Bowlby")
        self.assertEqual(hit["collection"], "Claude history")
        self.assertTrue(L.shown(hit).startswith("From your Claude history, word for word:"))
        self.assertIsNone(lib.find("What did Bowlby mean by a secure base?"))
        hit = lib.look_up("caregiver child explores")
        self.assertEqual(hit["heading"], "Claude")
        self.assertTrue(remember.author_text(hit).startswith(
            'No. That passage is from your Claude history, "Study notes: Attachment theory notes": written by Claude'))
        self.assertTrue(remember.source_of(hit).startswith("Claude, 2025-03-02"))
        mine = lib.look_up("Bowlby secure base")
        self.assertTrue(remember.source_of(mine).startswith("you in Claude, 2025-03-02"))
        self.assertEqual(lib.look_up("developmental psychology week")["heading"], "Project document: syllabus.md")

    def test_its_own_undo(self):
        e = ci.bring_in(self.zip, self.shelf)
        written = [os.path.join(self.shelf, p) for p in e["wrote"]]
        self.assertTrue(all(os.path.exists(p) for p in written))
        with self.assertRaises(ValueError):
            ci.bring_in(self.zip, self.shelf)
        self.assertTrue(own_shelf.remove(e["id"], self.shelf))
        self.assertFalse(any(os.path.exists(p) for p in written))

    def test_a_start_in_the_middle_reads_it_again(self):
        e = ci.bring_in(self.zip, self.shelf)
        os.remove(os.path.join(self.shelf, e["id"] + ".lib.sqlite"))
        e["state"] = own_shelf.READING
        own_shelf._write_entry(self.shelf, e)
        self.assertEqual(own_shelf.read(e, self.shelf)["state"], own_shelf.READY)

    def test_not_an_export(self):
        bad = os.path.join(self.d, "bad.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("users.json", "[]")
        with self.assertRaises(ValueError):
            ci.preview(bad)

    def test_the_command(self):
        self.assertEqual(ingest_claude.main(["--shelf", self.shelf, "add", self.zip]), 0)
        self.assertEqual([e["source"] for e in own_shelf.listing(self.shelf)], ["claude-export"])


if __name__ == "__main__":
    unittest.main()
