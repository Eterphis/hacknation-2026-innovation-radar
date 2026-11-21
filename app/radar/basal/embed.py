"""Text embeddings that run on a plain vCPU.

* `hashing` (default): character 3-5-gram hashing on folded text, 512 dims, L2-normalised. numpy only, no model
  download, deterministic, ~0.1 ms per text. Good for near-duplicates and topical similarity of Polish text
  (stems share n-grams), weak on synonyms.
* `fastembed[:<model>]`: ONNX Runtime on CPU via the optional `fastembed` package, default
  `intfloat/multilingual-e5-small` (384 dims, ~120 MB, downloaded once on first use). Better semantics,
  still no GPU. Enable with RADAR_EMBEDDER=fastembed.
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from functools import lru_cache

import numpy as np

DIM = 512


def fold(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", t).strip()


STOP = set("""a aby albo ale ani bardzo bez bo by byc byl byla bylo byly co czy dla do gdy go i ich ii in innych
inne jak jako je jego jej jest jesli juz ktora ktore ktory ktorych lub ma mi miedzy moze na nad nie niz o od oraz
po pod przez przy roku sa sie ich tak takze tego tej ten to tu tym w we wiec wraz wsrod z za ze zas dane
syntetyczne problem the of and for with in to on by an is are""".split())


class HashingEmbedder:
    """Word stems (first 6 letters, weight 2) + character 4-grams (weight 1), Polish stop words removed.
    Stems carry the topic, n-grams catch inflection ("kompozytów" ~ "kompozytowe")."""

    name = "hashing-stem6+char4"
    dim = DIM

    def _add(self, v: np.ndarray, token: str, weight: float) -> None:
        h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "little")
        v[h % self.dim] += weight if (h >> 31) & 1 else -weight

    def embed_one(self, text: str) -> np.ndarray:
        t = re.sub(r"\[[^\]]{0,40}\]", " ", text or "")  # drop "[DANE SYNTETYCZNE]"-style tags
        words = [w for w in re.sub(r"[^a-z0-9 ]+", " ", fold(t)).split() if len(w) > 2 and w not in STOP]
        v = np.zeros(self.dim, dtype=np.float32)
        for w in words:
            self._add(v, "s:" + w[:6], 2.0)
            g = f" {w} "
            for i in range(max(1, len(g) - 3)):
                self._add(v, g[i:i + 4], 1.0)
        norm = float(np.linalg.norm(v))
        return v / norm if norm else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self.embed_one(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)


class FastEmbedEmbedder:
    def __init__(self, model: str = "intfloat/multilingual-e5-small"):
        from fastembed import TextEmbedding  # optional dependency: pip install fastembed

        self._m = TextEmbedding(model_name=model)
        self.name = f"fastembed:{model}"
        self.dim = len(next(iter(self._m.embed(["x"]))))
        self._prefix = "query: " if "e5" in model else ""

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = np.array(list(self._m.embed([self._prefix + t for t in texts])), dtype=np.float32)
        return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


@lru_cache
def get_embedder():
    spec = os.environ.get("RADAR_EMBEDDER", "hashing")
    if spec.startswith("fastembed"):
        _, _, model = spec.partition(":")
        try:
            return FastEmbedEmbedder(model or "intfloat/multilingual-e5-small")
        except Exception as e:  # missing package or no network for the first download: degrade, don't crash
            import logging

            logging.getLogger(__name__).warning("fastembed unavailable (%s); using hashing embedder", e)
    return HashingEmbedder()


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: (d,) or (n,d); b: (m,d); vectors are L2-normalised."""
    return a @ b.T
