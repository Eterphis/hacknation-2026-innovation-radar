"""Text embeddings that run on a plain vCPU.

* `hashing` (default): character 3-5-gram hashing on folded text, 512 dims, L2-normalised. numpy only, no model
  download, deterministic, ~0.1 ms per text. Good for near-duplicates and topical similarity of Polish text
  (stems share n-grams), weak on synonyms.
* `fastembed[:<model>]`: ONNX Runtime on CPU via the optional `fastembed` package, default
  `intfloat/multilingual-e5-small` (384 dims, ~120 MB ONNX; the Docker image bakes it in at build time,
  FASTEMBED_CACHE_PATH). Better semantics, still no GPU. Enable with RADAR_EMBEDDER=fastembed.
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


# Section labels the harvester puts in every record (radar.record/v1 text_for_llm): not content, so not embedded.
# (Long real texts still share generic vocabulary: hashing median pair cosine 0.21 vs 0.08 on the short demo
# records, hence the per-embedder graph thresholds in CALIBRATION.)
BOILERPLATE = re.compile(r"(?i)\b(?:tytu[lł]|zajawka|opis projektu|jaki problem rozwi[aą]zuje projekt|efekt pracy|"
                         r"rezultaty?|cel projektu|s[lł]owa kluczowe|opis)\s*:\s*")


def clean(text: str | None) -> str:
    return BOILERPLATE.sub(" ", text or "")


class HashingEmbedder:
    """Word stems (first 6 letters, weight 2) + character 4-grams (weight 1), Polish stop words removed.
    Stems carry the topic, n-grams catch inflection ("kompozytów" ~ "kompozytowe")."""

    name = "hashing-stem6+char4"
    dim = DIM

    def _add(self, v: np.ndarray, token: str, weight: float) -> None:
        h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "little")
        v[h % self.dim] += weight if (h >> 31) & 1 else -weight

    def embed_one(self, text: str) -> np.ndarray:
        t = re.sub(r"\[[^\]]{0,40}\]", " ", clean(text))  # drop "[DANE SYNTETYCZNE]"-style tags
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


E5_SMALL = "intfloat/multilingual-e5-small"


def _register_e5_small() -> None:
    """multilingual-e5-small is not in fastembed's built-in list; its HF repo ships onnx/model.onnx."""
    from fastembed import TextEmbedding

    if any(m["model"] == E5_SMALL for m in TextEmbedding.list_supported_models()):
        return
    from fastembed.common.model_description import ModelSource, PoolingType

    TextEmbedding.add_custom_model(model=E5_SMALL, pooling=PoolingType.MEAN, normalization=True,
                                   sources=ModelSource(hf=E5_SMALL), dim=384, model_file="onnx/model.onnx")


class FastEmbedEmbedder:
    def __init__(self, model: str = E5_SMALL):
        from fastembed import TextEmbedding  # optional dependency: pip install fastembed

        if model == E5_SMALL:
            _register_e5_small()
        self._m = TextEmbedding(model_name=model, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))
        self.name = f"fastembed:{model}"
        self.dim = len(next(iter(self._m.embed(["x"]))))
        self._prefix = "query: " if "e5" in model else ""

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = np.array(list(self._m.embed([self._prefix + clean(t)[:2000] for t in texts])), dtype=np.float32)
        return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


# Cosine similarity lives on a different scale per embedder (hashing: unrelated ~0.05, near-duplicate ~0.9;
# e5-small: unrelated ~0.75, near-duplicate ~0.97). `calibration()` maps raw cosine to a common 0..1 scale for
# the label prototypes and gives the graph thresholds. Values measured on the 60 real records of
# eval/basal_gold.jsonl (pairwise and record x prototype percentiles; see .house/experiments.csv E-002..).
import json as _json

CALIBRATION = {
    # prototypes: raw cosine as before (lo/hi = identity); graph: p88 of real pairs (0.35), near-duplicates 0.9.
    # similar_floor/similar_q: the graph threshold adapts to the corpus (graph.similar_min): the similar_q quantile
    # of pairwise similarity, clamped to [similar_floor, similar_min]. Short demo records (median pair 0.08) get
    # ~0.2 as before PR #11, long real records (median 0.21) stay at 0.35.
    "hashing": {"lo": 0.0, "hi": 1.0, "similar_min": 0.35, "similar_floor": 0.2, "similar_q": 0.88, "dup_min": 0.9},
    # prototypes: lo = p5 of record x prototype cosine (0.78), hi = p95 of the best prototype (0.88);
    # graph: similar = p95 of real pairs (0.885), duplicate 0.95 (max of distinct real pairs was 0.936)
    "fastembed:intfloat/multilingual-e5-small": {"lo": 0.78, "hi": 0.88, "similar_min": 0.885, "similar_floor": 0.85,
                                                 "similar_q": 0.95, "dup_min": 0.95},
}


def calibration(name: str | None = None) -> dict:
    name = name or get_embedder().name
    if os.environ.get("RADAR_CALIBRATION"):  # experiments: JSON merged over the table entry
        return {**CALIBRATION.get(name, CALIBRATION["hashing"]), **_json.loads(os.environ["RADAR_CALIBRATION"])}
    if name in CALIBRATION:
        return CALIBRATION[name]
    return CALIBRATION["hashing"]  # hashing variants and uncalibrated models: raw cosine


def closeness(sim: float, name: str | None = None, similar_min: float | None = None) -> float:
    """Graph similarity on a common scale: 0 at the `similar` threshold, 1 at the near-duplicate threshold.
    `similar_min`: the threshold actually used for the corpus (graph.similar_min), default the calibrated one."""
    c = calibration(name)
    lo = c["similar_min"] if similar_min is None else similar_min
    return float(np.clip((sim - lo) / max(1e-6, c["dup_min"] - lo), 0.0, 1.0))


def rescale(sims: np.ndarray, name: str | None = None) -> np.ndarray:
    c = calibration(name)
    return np.clip((sims - c["lo"]) / (c["hi"] - c["lo"]), 0.0, 1.0)


@lru_cache
def get_embedder():
    spec = os.environ.get("RADAR_EMBEDDER", "hashing")
    if spec.startswith("fastembed"):
        _, _, model = spec.partition(":")
        try:
            return FastEmbedEmbedder(model or E5_SMALL)
        except Exception as e:  # missing package or no network for the first download: degrade, don't crash
            import logging

            logging.getLogger(__name__).warning("fastembed unavailable (%s); using hashing embedder", e)
    return HashingEmbedder()


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: (d,) or (n,d); b: (m,d); vectors are L2-normalised."""
    return a @ b.T
