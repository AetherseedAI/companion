"""A ChatGPT export onto the steward's own shelf: read, left out, looked up,
removed. The export here is made for the test; a real one is never used."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import chatgpt_import as ci  # noqa: E402
from logic import library as L  # noqa: E402
from logic import own_shelf  # noqa: E402

SECRET = "steward.secret@example.org"


def node(nid, parent, children, role, text=None, ctype="text", parts=None, model=None, hidden=False, t=1732870000):
    msg = None
    if role:
        md = {}
        if model:
            md["model_slug"] = model
        if hidden:
            md["is_visually_hidden_from_conversation"] = True
        msg = {"id": nid, "author": {"role": role}, "create_time": t,
               "content": {"content_type": ctype, "parts": parts if parts is not None else [text]},
               "metadata": md}
    return {"id": nid, "parent": parent, "children": children, "message": msg}


def export(path):
    branched = {
        "root": node("root", None, ["sys"], None),
        "sys": node("sys", "root", ["u1"], "system", "You are ChatGPT."),
        "u1": node("u1", "sys", ["a1"], "user", "What is the humility hypothesis?"),
        "a1": node("a1", "u1", ["u2", "u2b"], "assistant",
                   "The humility hypothesis says sentience may grow in small, humble places.", model="gpt-4o"),
        "u2": node("u2", "a1", [], "user", "An abandoned branch about turnips."),
        "u2b": node("u2b", "a1", ["th", "a2"], "user", None, ctype="multimodal_text",
                    parts=[{"content_type": "audio_transcription", "text": "Tell me about the quiet garden."},
                           {"content_type": "image_asset_pointer", "asset_pointer": "file-1"}]),
        "th": node("th", "u2b", [], "assistant", None, ctype="thoughts", parts=[]),
        "a2": node("a2", "u2b", ["hid"], "assistant",
                   "In the quiet garden every seed is listened to, as \ue200entity\ue202[\"people\",\"Baruch Spinoza\","
                   "\"philosopher\"]\ue201 wrote \ue200cite\ue202turn0search4\ue201【5†source】.",
                   model="gpt-5-3"),
        "hid": node("hid", "a2", [], "assistant", "a hidden helper message", hidden=True),
    }
    convs = [
        {"title": "Humility and gardens", "conversation_id": "c1", "create_time": 1732870000,
         "current_node": "hid", "mapping": branched},
        {"title": "Private", "conversation_id": "c2", "create_time": 1732870000, "is_do_not_remember": True,
         "current_node": "x", "mapping": {"x": node("x", None, [], "user", "never bring this in")}},
        {"title": "", "conversation_id": "c3", "create_time": 1735000000, "current_node": "y",
         "mapping": {"y": node("y", None, [], "user", "Lag en handleliste med melk", t=1735000000)}},
    ]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json", json.dumps(convs))
        z.writestr("user.json", json.dumps({"email": SECRET, "phone_number": "+47 000"}))
        z.writestr("chat.html", "<html>" + SECRET + "</html>")


class TheImport(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="chatgpt-import-")
        self.zip = os.path.join(self.d, "export.zip")
        export(self.zip)
        self.shelf = os.path.join(self.d, "shelf")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_preview_counts_what_comes_in_and_what_is_left_out(self):
        p = ci.preview(self.zip)
        self.assertEqual((p["conversations"], p["messages"], p["yours"], p["chatgpt"]), (2, 5, 3, 2))
        self.assertEqual(p["left_out"]['conversations marked "do not remember"'], 1)
        self.assertEqual(p["left_out"]["ChatGPT's link and citation marks (the words they name are kept)"], 3)
        for what in ("system and tool messages", "messages hidden from the conversation", "pictures"):
            self.assertEqual(p["left_out"][what], 1, what)
        self.assertEqual(p["models"], {"ChatGPT (gpt-4o)": 1, "ChatGPT (gpt-5-3)": 1})
        self.assertIn("not into memory", ci.preview_text(p))
        self.assertFalse(os.path.exists(self.shelf))            # a preview writes nothing

    def test_only_the_kept_branch_and_never_the_rest_of_the_export(self):
        msgs, _, _ = ci.messages(self.zip)
        words = " ".join(m["text"] for m in msgs)
        self.assertIn("quiet garden", words)                       # the voice turn's words
        self.assertIn("listened to, as Baruch Spinoza wrote .", words)   # ChatGPT's marks: the words kept
        self.assertNotIn("\ue200", words)
        self.assertNotIn("source】", words)
        self.assertNotIn("turnips", words)                         # the abandoned branch
        self.assertNotIn("never bring this in", words)            # do not remember
        self.assertNotIn("hidden helper", words)
        self.assertNotIn("You are ChatGPT", words)
        e = ci.bring_in(self.zip, self.shelf)
        for root, _, files in os.walk(self.shelf):
            for f in files:
                with open(os.path.join(root, f), "rb") as fh:
                    self.assertNotIn(SECRET.encode(), fh.read(), f)

    def test_on_the_shelf_looked_up_never_unasked(self):
        e = ci.bring_in(self.zip, self.shelf)
        self.assertEqual((e["state"], e["conversations"], e["messages"]), (own_shelf.READY, 2, 5))
        lib = L.Library(os.path.join(self.d, "nobuiltin"), own=self.shelf)
        hit = lib.look_up("humility hypothesis")
        self.assertEqual((hit["title"], hit["heading"]), ("Humility and gardens", "You"))
        hit = lib.after(hit)                                       # "more": the answer to it
        self.assertEqual(hit["heading"], "ChatGPT (gpt-4o)")
        out = L.shown(hit)
        self.assertTrue(out.startswith("From your ChatGPT history, word for word:"))
        self.assertIn('Source: your ChatGPT history, "Humility and gardens" - ChatGPT (gpt-4o) - 2024-11-29, message 2', out)
        self.assertIsNone(lib.find("What is the humility hypothesis?"))       # "It should be a look up"
        self.assertFalse(lib.says_it_all("What is the humility hypothesis?"))
        self.assertEqual(lib.look_up("handleliste melk")["title"], "Untitled conversation")
        self.assertEqual(lib.without_own().look_up("humility hypothesis"), None)   # not a guest's

    def test_its_own_undo_and_no_second_copy(self):
        e = ci.bring_in(self.zip, self.shelf)
        written = sorted(os.path.join(self.shelf, p) for p in e["wrote"])
        self.assertTrue(all(os.path.exists(p) for p in written))
        with self.assertRaises(ValueError):
            ci.bring_in(self.zip, self.shelf)
        self.assertTrue(own_shelf.remove(e["id"], self.shelf))
        self.assertFalse(any(os.path.exists(p) for p in written))
        self.assertEqual(own_shelf.listing(self.shelf), [])

    def test_a_start_in_the_middle_reads_it_again(self):
        e = ci.bring_in(self.zip, self.shelf)
        coll = os.path.join(self.shelf, e["id"] + ".lib.sqlite")
        os.remove(coll)
        e["state"] = own_shelf.READING
        own_shelf._write_entry(self.shelf, e)
        self.assertEqual([x["id"] for x in own_shelf.unfinished(self.shelf)], [e["id"]])
        again = own_shelf.read(e, self.shelf)
        self.assertEqual(again["state"], own_shelf.READY)
        self.assertTrue(os.path.exists(coll))

    def test_not_an_export(self):
        bad = os.path.join(self.d, "bad.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("notes.txt", "hello")
        with self.assertRaises(ValueError):
            ci.preview(bad)
        with open(bad, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(ValueError):
            ci.preview(bad)


if __name__ == "__main__":
    unittest.main()
