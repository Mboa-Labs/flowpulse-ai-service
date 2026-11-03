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

    options = {"num_thread": settings.llm_threads} if settings.llm_threads else None
    return ollama.Client(host=settings.ollama_url).embed(model=settings.embed_model, input=[text], options=options)["embeddings"][0]


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


def documents() -> list[dict]:
    """Inventaire de sources.csv, avec le nombre de passages indexés par document."""
    import csv

    manifest = settings.chroma_dir.parent / "sources.csv"
    if not manifest.exists():
        return []
    counts: dict[str, int] = {}
    try:
        for name in COLLECTIONS:
            try:
                metas = _client().get_collection(name).get(include=["metadatas"])["metadatas"] or []
            except Exception:
                continue
            for m in metas:
                doc = m.get("doc_id", "")
                counts[doc] = counts.get(doc, 0) + 1
    except Exception:
        pass
    with manifest.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        {
            "id": r["id"], "titre": r["titre"], "reference": r["reference"], "type": r["type"],
            "domaine": r["domaine"], "pays": r["pays"], "statut": r["statut"], "fichier": r["fichier"],
            "url_source": r["url_source"], "notes": r["notes"], "passages": counts.get(r["id"], 0),
        }
        for r in rows
    ]


INDEXATION: dict = {"etat": "inactive", "debut": None, "fin": None, "journal": ""}


def reindex(include_all: bool = True) -> dict:
    """Relance scripts/ingest.py en tâche de fond (embeddings Ollama) ; l'état se lit dans INDEXATION."""
    import subprocess
    import sys
    import threading
    import time

    if INDEXATION["etat"] == "en_cours":
        return INDEXATION
    script = settings.chroma_dir.parent / "scripts" / "ingest.py"
    if not script.exists():
        raise FileNotFoundError(f"Script d'indexation introuvable : {script}")
    cmd = [sys.executable, str(script)] + (["--all"] if include_all else [])
    env = {**__import__("os").environ, "FLOWPULSE_CHROMA_DIR": str(settings.chroma_dir),
           "FLOWPULSE_OLLAMA_URL": settings.ollama_url, "FLOWPULSE_EMBED_MODEL": settings.embed_model,
           "PYTHONIOENCODING": "utf-8"}
    INDEXATION.update(etat="en_cours", debut=time.time(), fin=None, journal="")

    def worker():
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=3600)
            INDEXATION.update(etat="terminee" if out.returncode == 0 else "echec", journal=(out.stdout + out.stderr)[-4000:])
        except Exception as e:
            INDEXATION.update(etat="echec", journal=str(e))
        finally:
            INDEXATION["fin"] = time.time()
            _client.cache_clear()

    threading.Thread(target=worker, daemon=True).start()
    return INDEXATION
