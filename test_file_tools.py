"""Her file tools (logic/file_tools.py): what is read as a request, what is
written, and where she cannot write."""
import os
import shutil
import tempfile
import unittest

from intent_detection import detect_intent
from logic import file_tools as F
from logic import no_tool
from logic import workspace as W


class TheWords(unittest.TestCase):

    def intent(self, text):
        i = F.parse(text)
        return (i["intent"], i["captures"]) if i else None

    def test_saves(self):
        self.assertEqual(self.intent("save it as story.md"),
                         ("file_save", ("story.md", None, None, "last")))
        self.assertEqual(self.intent("put it in the builder folder in your workspace"),
                         ("file_save", (None, "builder", None, "last")))
        self.assertEqual(self.intent('save that as "My poem"'),
                         ("file_save", ("My poem", None, None, "last")))
        self.assertEqual(self.intent("write a poem about rain and save it as rain.md")[1][3], "after")
        self.assertEqual(self.intent("try writing the story in an .md format")[1][3], "after")
        i = self.intent("Write a story about Aksel. save the file in a docx file and name it "
                        "The tiny travels of Nova and Aksel")
        self.assertEqual(i, ("file_save", ("The tiny travels of Nova and Aksel", None, "docx", "after")))

    def test_the_other_tools(self):
        self.assertEqual(self.intent("append it to story.md"), ("file_append", ("story.md", None)))
        self.assertEqual(self.intent("add to the file log.md: fed the cat"),
                         ("file_append", ("log.md", "fed the cat")))
        self.assertEqual(self.intent("write to a new file ideas.md: a bee house"),
                         ("file_write", ("ideas.md", "a bee house")))
        self.assertEqual(self.intent("make a folder called stories"), ("folder_make", ("stories",)))
        self.assertEqual(self.intent("move story.md to stories"), ("file_move", ("story.md", "stories")))
        self.assertEqual(self.intent("rename story.md to nova.md"), ("file_move", ("story.md", "nova.md")))
        self.assertEqual(self.intent("delete the file old.md"), ("file_delete", ("old.md",)))

    def test_ordinary_words_are_no_request(self):
        for text in ("I saved the day", "save money on groceries", "keep it short",
                     "put it simply", "write a poem about the sea", "write it down for me",
                     "delete that thought", "the story is saved in my heart",
                     "remove 2 from my to-do list", "add milk to my to-do list",
                     "save this as a note", "write a note: buy oats", "Move to the next one",
                     "I keep this in my folder of memories", "Put it on my tab"):
            with self.subTest(text=text):
                self.assertIsNone(F.parse(text))

    def test_the_notes_and_to_dos_keep_their_own_tools(self):
        self.assertEqual(detect_intent("write a note: buy oats")["intent"], "note_write")
        self.assertEqual(detect_intent("save this as a note")["intent"], "note_write")
        self.assertEqual(detect_intent("add milk to my to-do list")["intent"], "todo_add")

    def test_names(self):
        self.assertEqual(F.file_name("story"), ("story.md", None))
        self.assertEqual(F.file_name("story.txt"), ("story.txt", None))
        name, note = F.file_name("Nova.docx")
        self.assertEqual(name, "Nova.md")
        self.assertIn("can't make .docx", note)
        self.assertEqual(F.file_name('The "Nova" story')[0], "The Nova story.md")
        self.assertEqual(F.file_name(None, None, "# A Tale\n\nOnce")[0], "A Tale.md")
        self.assertEqual(F.file_name("x", "txt")[0], "x.txt")

    def test_capability_questions(self):
        for q in ("what types of files can you create? can you make a docx file?",
                  "Can you make a PDF?", "what files can you make", "can you create files"):
            self.assertTrue(F.asks_capability(q), q)
        for q in ("can you make a pdf about bees", "what is a docx", "write a story"):
            self.assertFalse(F.asks_capability(q), q)
        self.assertIn("writer trust level", F.capability_text("observer", False))
        self.assertNotIn("writer trust level", F.capability_text("writer", True))

    def test_claims(self):
        for r in ("Done! The file is now saved as a .docx document in your workspace.",
                  "I saved the file in your local workspace, in the notes folder.",
                  "It's at aetherseed-workspace/builder/story.docx",
                  "I'll save it as a .docx file named Nova."):
            self.assertTrue(F.claims_a_file_action(r), r)
        for r in ("Once upon a time Nova saved a snail.", "I can't see your files.",
                  "The bee moved to a new flower."):
            self.assertFalse(F.claims_a_file_action(r), r)

    def test_the_follow_ups_get_the_line(self):
        for q in ("let me know when its done", "where did you save the story ?",
                  "show me the filepath because I cant find it", "put it in the builder folder",
                  "now write the story", "is it saved?"):
            self.assertEqual(no_tool.line_for(q), no_tool.NOTHING_SAVED, q)
        self.assertIsNone(no_tool.line_for("how are you today?"))


class TheWorkspace(unittest.TestCase):

    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="ws-")
        W.ensure(self.ws)
        self.out = tempfile.mkdtemp(prefix="out-")

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)
        shutil.rmtree(self.out, ignore_errors=True)

    def test_a_save_is_said_with_its_path_and_never_writes_over(self):
        r = F.save_new(self.ws, "story.md", "Nova hummed.", "writer")
        self.assertEqual(r, "Saved: story.md (13 bytes).")
        self.assertEqual(open(os.path.join(self.ws, "story.md")).read(), "Nova hummed.\n")
        r = F.save_new(self.ws, "story.md", "Other.", "writer")
        self.assertIn("already there", r)
        self.assertEqual(open(os.path.join(self.ws, "story.md")).read(), "Nova hummed.\n")

    def test_nothing_to_save(self):
        self.assertIn("Nothing was written", F.save_new(self.ws, "a.md", "  ", "writer"))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "a.md")))

    def test_paths_stay_inside(self):
        os.symlink(self.out, os.path.join(self.ws, "out"))
        for rel in ("../x.md", "out/x.md", "~/x.md", "a/../../x.md"):
            with self.subTest(rel=rel):
                r = F.save_new(self.ws, rel, "x", "autonomous")
                self.assertNotIn("Saved:", r)
        self.assertEqual(os.listdir(self.out), [])
        # a leading slash is read inside the workspace, as the editor reads it
        self.assertEqual(F.save_new(self.ws, "/etc/x.md", "x", "autonomous"), "Saved: etc/x.md (2 bytes).")

    def test_a_folder_above_her_level_is_closed(self):
        r = F.save_new(self.ws, "builder/x.md", "x", "writer")
        self.assertIn("opens at the builder trust level", r)
        self.assertFalse(os.path.exists(os.path.join(self.ws, "builder", "x.md")))
        self.assertIn("Saved:", F.save_new(self.ws, "writer/x.md", "x", "writer"))
        self.assertIn("opens at the builder", F.move(self.ws, "writer/x.md", "builder", "writer"))

    def test_append(self):
        F.save_new(self.ws, "log.md", "one", "writer")
        self.assertIn("added to the end", F.append(self.ws, "log.md", "two", "writer"))
        self.assertEqual(open(os.path.join(self.ws, "log.md")).read(), "one\n\ntwo\n")

    def test_move_and_folders(self):
        F.save_new(self.ws, "story.md", "x", "writer")
        self.assertEqual(F.make_folder(self.ws, "stories", "writer"), "Made the folder stories/.")
        self.assertEqual(F.move(self.ws, "story.md", "stories", "writer"),
                         "Moved: story.md -> stories/story.md.")
        self.assertIn("no file", F.move(self.ws, "gone.md", "stories", "writer"))
        self.assertIn("stay", F.to_trash(self.ws, "observer", "autonomous"))

    def test_a_delete_goes_to_the_trash(self):
        F.save_new(self.ws, "old.md", "keep me", "writer")
        r = F.to_trash(self.ws, "old.md", "writer")
        self.assertTrue(r.startswith("Moved to the trash: old.md"), r)
        self.assertFalse(os.path.exists(os.path.join(self.ws, "old.md")))
        kept = os.listdir(os.path.join(self.ws, ".trash"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(open(os.path.join(self.ws, ".trash", kept[0])).read(), "keep me\n")

    def test_the_unit_lines_are_not_saved_again(self):
        text = "# Tale\n\nOnce.\n\nSaved: tale.md (12 bytes).\n\n(From the unit: nothing was saved)"
        self.assertEqual(F.without_unit_lines(text), "# Tale\n\nOnce.")


if __name__ == "__main__":
    unittest.main()
