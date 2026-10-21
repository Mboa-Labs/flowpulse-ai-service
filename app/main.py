"""Service IA FlowPulse : pipeline de données, modèles, agents et base de connaissances.

Ce socle expose la santé du service et la recherche dans la base de connaissances.
Les routes des agents (/ai/assistant, /ai/simulate…) s'ajoutent ici au fil des lots.
"""

from dataclasses import asdict
from typing import Optional

import httpx
from fastapi import FastAPI, Query
from pydantic import BaseModel

from app import kb
from app.config import settings

app = FastAPI(title="FlowPulse AI service", version="0.1.0")


class PassageOut(BaseModel):
    texte: str
    score: float
    doc_id: str
    titre: str
    reference: str
    article: str
    collection: str


@app.get("/health")
def health() -> dict:
    """État du service et de ses dépendances (Ollama, base de connaissances)."""
    try:
        models = httpx.get(f"{settings.ollama_url}/api/tags", timeout=3).json().get("models", [])
        ollama = {"ok": True, "models": [m["name"] for m in models]}
    except Exception as e:
        ollama = {"ok": False, "error": str(e)}
    try:
        kb_stats = {"ok": True, "collections": kb.stats()}
    except Exception as e:
        kb_stats = {"ok": False, "error": str(e)}
    return {"status": "ok", "ollama": ollama, "knowledge_base": kb_stats}


@app.get("/ai/kb/search", response_model=list[PassageOut])
def kb_search(
    q: str = Query(..., min_length=3, description="Question ou décision à vérifier"),
    n: int = Query(5, ge=1, le=20),
    collection: str = Query("kb_reglementaire", pattern="^(kb_reglementaire|kb_framework|kb_manques)$"),
    domaine: Optional[str] = None,
    pays: Optional[str] = None,
) -> list[PassageOut]:
    """Passages les plus proches, avec document et article, pour que l'agent cite ses sources."""
    return [PassageOut(**asdict(p)) for p in kb.search(q, n=n, collection=collection, domaine=domaine, pays=pays)]
