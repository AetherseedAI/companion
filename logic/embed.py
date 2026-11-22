"""Sentence embeddings for her memory: what a turn is ABOUT, not its words.

all-MiniLM-L6-v2 (Apache-2.0; 6 layers, 384 numbers a sentence), run with
numpy alone - no new package on the unit, which has no network - from its
safetensors weights and its tokenizer.json (the `tokenizers` package the token
guard already uses). Mean-pooled over the tokens and normalised, as the model
is meant to be used, so the dot product of two vectors is their cosine.

The model files are not in the repository (90 MB): the unit's own setting,
put in place by whoever installs it (docs/INSTALL.md):

    /var/lib/aetherseed/embed/model.safetensors   sha256 53aa5117...128d9db
    /var/lib/aetherseed/embed/tokenizer.json      sha256 be50c362...2572037

Without them nothing here is used: ranking stays by words.
"""
import json
import os
import struct

import numpy as np

MODEL_DIR = os.environ.get("AETHERSEED_EMBED_DIR", "/var/lib/aetherseed/embed")
MODEL_SHA256 = "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db"
TOKENIZER_SHA256 = "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"
DIM = 384
LAYERS = 6
HEADS = 12
MAX_TOKENS = 128
EPS = 1e-12

_DTYPES = {"F32": np.float32, "I64": np.int64}


def _load_safetensors(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
        base = 8 + n
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    out = {}
    for k, v in header.items():
        if k == "__metadata__":
            continue
        a, b = v["data_offsets"]
        out[k] = np.frombuffer(raw[base + a:base + b], dtype=_DTYPES[v["dtype"]]).reshape(v["shape"])
    return out


def _ln(x, w, b):
    m = x.mean(-1, keepdims=True)
    v = ((x - m) ** 2).mean(-1, keepdims=True)
    return (x - m) / np.sqrt(v + EPS) * w + b


def _gelu(x):
    # The tanh form of GELU: numpy has no erf, and the exact form through
    # math.erf element by element made a sentence cost ~40 ms more. Measured
    # against the exact form on the same sentences: cosine 0.99999+.
    return 0.5 * x * (1.0 + np.tanh(0.7978845608028654 * (x + 0.044715 * x ** 3)))


class Embedder:
    def __init__(self, model_dir=MODEL_DIR):
        from tokenizers import Tokenizer
        self.w = _load_safetensors(os.path.join(model_dir, "model.safetensors"))
        self.tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.tok.enable_truncation(MAX_TOKENS)
        self.tok.no_padding()

    def _p(self, name):
        return self.w[name]

    def encode(self, texts):
        """Unit vectors, one row a text."""
        if isinstance(texts, str):
            texts = [texts]
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            out[i] = self._one(t or "")
        return out

    def _one(self, text):
        p = self._p
        ids = np.array(self.tok.encode(text).ids, dtype=np.int64)
        n = len(ids)
        x = (p("embeddings.word_embeddings.weight")[ids]
             + p("embeddings.position_embeddings.weight")[:n]
             + p("embeddings.token_type_embeddings.weight")[0])
        x = _ln(x, p("embeddings.LayerNorm.weight"), p("embeddings.LayerNorm.bias"))
        hd = DIM // HEADS
        for L in range(LAYERS):
            pre = "encoder.layer.%d." % L

            def lin(name, h):
                return h @ p(pre + name + ".weight").T + p(pre + name + ".bias")
            q = lin("attention.self.query", x).reshape(n, HEADS, hd).transpose(1, 0, 2)
            k = lin("attention.self.key", x).reshape(n, HEADS, hd).transpose(1, 0, 2)
            v = lin("attention.self.value", x).reshape(n, HEADS, hd).transpose(1, 0, 2)
            s = q @ k.transpose(0, 2, 1) / np.sqrt(hd)
            s = np.exp(s - s.max(-1, keepdims=True))
            s /= s.sum(-1, keepdims=True)
            a = (s @ v).transpose(1, 0, 2).reshape(n, DIM)
            x = _ln(lin("attention.output.dense", a) + x,
                    p(pre + "attention.output.LayerNorm.weight"), p(pre + "attention.output.LayerNorm.bias"))
            h = _gelu(lin("intermediate.dense", x))
            x = _ln(lin("output.dense", h) + x,
                    p(pre + "output.LayerNorm.weight"), p(pre + "output.LayerNorm.bias"))
        v = x.mean(0)
        return v / (np.linalg.norm(v) or 1.0)


_SHARED = None


def shared():
    """The one embedder of the process, or None when the model is not installed."""
    global _SHARED
    if _SHARED is None:
        try:
            _SHARED = Embedder()
        except Exception as e:
            print(f"[embed] not available: {e!r}", flush=True)
            _SHARED = False
    return _SHARED or None
