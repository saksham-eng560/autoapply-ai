"""Text embeddings for semantic job <-> resume matching (pgvector, 1536 dims).

* ``EMBEDDING_PROVIDER=openai``: OpenAI ``text-embedding-3-small`` (1536 dims).
* ``EMBEDDING_PROVIDER=local`` (default): deterministic feature-hashing embedder over words,
  bigrams and known skills. It needs no API key and gives useful keyword-level similarity.

Keep one provider per deployment: vectors from different providers are not comparable
(run ``python scripts/migrate.py --reembed`` after switching).
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter
from itertools import pairwise

import httpx

from app.config import settings
from app.services.text_utils import extract_skills, tokenize

logger = logging.getLogger(__name__)

DIM = settings.EMBEDDING_DIM


def _bucket(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % DIM, (1.0 if (value >> 63) & 1 else -1.0)


def local_embedding(text: str) -> list[float]:
    tokens = tokenize(text)
    features: Counter[str] = Counter()
    for tok in tokens:
        features[f"w:{tok}"] += 1.0
    for a, b in pairwise(tokens):
        features[f"b:{a} {b}"] += 0.5
    for skill in extract_skills(text):
        features[f"s:{skill}"] += 3.0  # skills dominate the representation
    vec = [0.0] * DIM
    for feature, weight in features.items():
        idx, sign = _bucket(feature)
        vec[idx] += sign * (1.0 + math.log(weight))
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def openai_embeddings(texts: list[str]) -> list[list[float]]:
    response = httpx.post(
        f"{settings.OPENAI_BASE_URL.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={"model": settings.OPENAI_EMBEDDING_MODEL, "input": [t[:8000] for t in texts], "dimensions": DIM},
        timeout=60,
    )
    response.raise_for_status()
    data = sorted(response.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.EMBEDDING_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        try:
            return openai_embeddings(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI embeddings failed (%s); using local embeddings", exc)
    return [local_embedding(t) for t in texts]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)
