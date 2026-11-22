"""Three small harness fixes found on 16 Nov (trial-self-harness-baseline)."""
import unittest

from logic import knowledge as K
from logic import token_budget as T


class TheFixes(unittest.TestCase):

    def test_a_list_is_not_cut_after_its_first_item(self):
        text = "1. Mustardseed - the charter.\n\n2. AetherRoot - memory.\n\n3. AetherSpark - tools."
        self.assertEqual(T.first_paragraph(text), (text, False))
        self.assertEqual(T.first_paragraph("- Red.\n\n- Blue."), ("- Red.\n\n- Blue.", False))
        # after the list, a blank line still ends the answer
        self.assertEqual(T.first_paragraph("1. Red.\n2. Blue.\nThat is all.\n\nAnything else?"),
                         ("1. Red.\n2. Blue.\nThat is all.", True))
        self.assertEqual(T.first_paragraph("Oslo.\n\nI hope that helps!"), ("Oslo.", True))

    def test_a_bare_unverified_opener_is_taken_off(self):
        self.assertEqual(T.strip_leading_artefacts("Unverified. I cannot provide a link."),
                         ("I cannot provide a link.", 1))
        self.assertEqual(T.strip_leading_artefacts("Unverified claims spread fast."),
                         ("Unverified claims spread fast.", 0))
        self.assertTrue(T.opening_may_be_artefact("Unver"))
        self.assertFalse(T.opening_may_be_artefact("Oslo"))

    def test_the_tags_question_finds_its_line(self):
        lines = K.load_knowledge().lines_for("What does a tag on one of your memories mean?")
        self.assertTrue(any("can carry a tag" in l for l in lines), lines)


if __name__ == "__main__":
    unittest.main()
