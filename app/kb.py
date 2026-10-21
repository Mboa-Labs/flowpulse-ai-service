"""Accès en lecture à la base de connaissances (ChromaDB alimentée par knowledge-base/scripts/ingest.py)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from app.config import settings

COLLECTIONS = ("kb_reglementaire", "kb_framework", "kb_manques")


@dataclass
class Passage:
    """Passage cité par un agent : le texte et de quoi retrouver la source exacte."""

    texte: str
    score: float
    doc_id: str
    titre: str
    reference: str
    article: str
    collection: str

    @classmethod
    def from_chroma(cls, document: str, metadata: dict[str, Any], distance: float, collection: str) -> "Passage":
        return cls(
            texte=document,
            score=round(1 - distance, 4),  # distance cosinus → similarité
            doc_id=metadata.get("doc_id", metadata.get("id", "")),
            titre=metadata.get("titre", metadata.get("description", "")),
            reference=metadata.get("reference", ""),
            article=metadata.get("article", ""),
            collection=collection,
        )


@lru_cache(maxsize=1)
def _client():
    import chromadb

    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def embed(text: str) -> list[float]:
    import ollama

    return ollama.Client(host=settings.ollama_url).embed(model=settings.embed_model, input=[text])["embeddings"][0]


def stats() -> dict[str, int]:
    client = _client()
    out = {}
    for name in COLLECTIONS:
        try:
            out[name] = client.get_collection(name).count()
        except Exception:
            out[name] = 0
    return out


def search(question: str, n: int = 5, collection: str = "kb_reglementaire",
           domaine: Optional[str] = None, pays: Optional[str] = None) -> list[Passage]:
    """Recherche sémantique ; filtres optionnels sur les métadonnées de sources.csv."""
    try:
        col = _client().get_collection(collection)
    except Exception:
        return []
    count = col.count()
    if count == 0:
        return []

    filters = [{"domaine": domaine}] if domaine else []
    if pays:
        filters.append({"country": pays})
    where = None if not filters else filters[0] if len(filters) == 1 else {"$and": filters}

    result = col.query(query_embeddings=[embed(question)], n_results=min(n, count), where=where,
                       include=["documents", "metadatas", "distances"])
    return [
        Passage.from_chroma(doc, meta, dist, collection)
        for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
    ]
