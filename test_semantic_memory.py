"""Turns found by meaning as well as by words - on where the model is installed.

    python3 -m unittest test_semantic_memory -v

The real model is not needed: a stand-in embedder maps texts to fixed vectors.
"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aetherroot  # noqa: E402
from logic.semantic_index import SemanticIndex  # noqa: E402

TOPICS = {"stone": 0, "masonry": 0, "wall": 0, "rome": 1, "roman": 1, "tomato": 2}


class Fake:
    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for n, t in enumerate(texts):
            hit = [i for w, i in TOPICS.items() if w in (t or "").lower()]
            out[n, hit[0] if hit else 383] = 1.0
        return out


class ByMeaning(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sem-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.root = aetherroot.AetherRoot(self.home)
        self.a = self.root.store_interaction("what do you know about building with stones",
                                             "Stone is durable.")
        self.b = self.root.store_interaction("when did the roman empire begin", "27 BCE.")

    def on(self):
        self.root.config["semantic_memory"] = True
        self.root._semantic = SemanticIndex(self.root.root_dir, Fake())
        for i, q in ((self.a, "what do you know about building with stones"),
                     (self.b, "when did the roman empire begin")):
            self.root._semantic.add(i, q)

    def test_on_by_default_and_off_without_the_model(self):
        self.assertTrue(self.root.config["semantic_memory"])
        self.assertEqual((self.root.config["semantic_threshold"], self.root.config["semantic_max"]),
                         (0.5, 3))
        from logic import embed
        self.addCleanup(setattr, embed, "_SHARED", embed._SHARED)
        embed._SHARED = False            # the model is not installed
        self.root._semantic = None
        self.assertIsNone(self.root.semantic())
        self.assertNotIn("stones", self.root.retrieve_context("Tell me about masonry walls"))

    def test_on_a_turn_that_shares_no_word_is_found(self):
        self.on()
        ctx = self.root.retrieve_context("Tell me about masonry walls")
        self.assertIn("building with stones", ctx)
        self.assertNotIn("roman empire", ctx)

    def test_small_talk_finds_nothing_by_meaning(self):
        self.on()
        self.assertEqual(self.root._by_meaning("Hi!", [], set()), [])

    def test_the_index_is_kept(self):
        self.on()
        again = SemanticIndex(self.root.root_dir, Fake())
        self.assertTrue(again.has(self.a) and again.has(self.b))


if __name__ == "__main__":
    unittest.main()
