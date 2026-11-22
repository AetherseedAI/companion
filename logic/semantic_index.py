"""Her turns by meaning: one vector a turn (its question), kept beside memory.db.

    ~/.aetherseed/aetherroot/semantic.npz     ids (int64), vectors (float32, 384)

Built once by tools/semantic_index.py (on a unit with this model about 0.7 s a
turn), then kept up to date: a turn stored later is added after its answer has
gone out, never on the way to it. A turn that is not in the index is simply not
found by meaning; its words still find it.
"""
import os
import threading

import numpy as np

FILE = "semantic.npz"


class SemanticIndex:
    def __init__(self, root_dir, embedder):
        self.path = os.path.join(str(root_dir), FILE)
        self.embedder = embedder
        self.lock = threading.Lock()
        self.ids = np.zeros(0, dtype=np.int64)
        self.vecs = np.zeros((0, 384), dtype=np.float32)
        try:
            d = np.load(self.path)
            self.ids, self.vecs = d["ids"].astype(np.int64), d["vecs"].astype(np.float32)
        except (OSError, KeyError, ValueError):
            pass
        self._pos = {int(i): k for k, i in enumerate(self.ids)}

    def __len__(self):
        return len(self.ids)

    def has(self, episode_id):
        return int(episode_id) in self._pos

    def add(self, episode_id, text, save=True):
        v = self.embedder.encode(text or "")[0]
        with self.lock:
            if int(episode_id) in self._pos:
                return
            self.ids = np.append(self.ids, np.int64(episode_id))
            self.vecs = np.vstack([self.vecs, v[None, :]])
            self._pos[int(episode_id)] = len(self.ids) - 1
            if save:
                self.save()

    def add_later(self, episode_id, text):
        threading.Thread(target=self._quiet_add, args=(episode_id, text), daemon=True).start()

    def _quiet_add(self, episode_id, text):
        try:
            self.add(episode_id, text)
        except Exception as e:
            print(f"[semantic] turn {episode_id} not indexed: {e!r}", flush=True)

    def save(self):
        tmp = self.path + ".tmp.npz"
        np.savez(tmp, ids=self.ids, vecs=self.vecs)
        os.replace(tmp, self.path)

    def similar(self, query_vec, candidate_ids, threshold, k):
        """[(sim, id)] of the candidates at or above threshold, best first."""
        with self.lock:
            rows = [(self._pos[int(i)], int(i)) for i in candidate_ids if int(i) in self._pos]
            if not rows:
                return []
            idx = np.array([r[0] for r in rows])
            sims = self.vecs[idx] @ query_vec
        out = [(float(s), rows[n][1]) for n, s in enumerate(sims) if s >= threshold]
        out.sort(reverse=True)
        return out[:k]
