"""Service IA FlowPulse : pipeline de données, modèles, agents et base de connaissances.

Routes : santé, recherche dans la base de connaissances, superviseur (Orchestrator),
surveillance (Watcher + Optimizer + Policy), recommandations, traces et manques réglementaires.
"""

from dataclasses import asdict
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app import kb
from app.agents import data, orchestrator, store, watcher
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


# ---------------------------------------------------------------- Agents

class Question(BaseModel):
    question: str


class Decision(BaseModel):
    decision: Literal["appliquer", "rejeter"]
    motif: Optional[str] = None


@app.get("/ai/zones")
def zones() -> list[dict]:
    """Vue d'ensemble par zone : trafic, flotte et niveau d'alerte (données de démonstration)."""
    out = []
    for z in data.zones():
        t, f = data.traffic(z), data.fleet(z)
        out.append({"zone": z, **t, **(f or {}), "niveau": watcher.level(t["niveau_congestion"]) or "FLUIDE"})
    return out


@app.post("/ai/assistant")
def assistant(body: Question) -> dict:
    """Question en langage naturel au superviseur ; la réponse renvoie ses sources et l'identifiant de trace."""
    return asdict(orchestrator.ask(body.question))


@app.post("/ai/watcher/run")
def run_watcher() -> dict:
    """Lance un passage de surveillance : alertes, puis recommandations pour les zones saturées."""
    trace_id, alerts = watcher.run()
    return {"trace_id": trace_id, "alertes": [asdict(a) for a in alerts]}


@app.get("/ai/watcher/last")
def last_watcher_run() -> dict:
    """Résultat du dernier passage de surveillance (pour l'affichage des alertes)."""
    return {"trace_id": watcher.LAST_RUN["trace_id"], "alertes": [asdict(a) for a in watcher.LAST_RUN["alertes"]]}


@app.get("/ai/recommendations")
def list_recommendations() -> list[dict]:
    return [asdict(r) for r in store.RECOMMENDATIONS.values()]


@app.get("/ai/recommendations/{reco_id}")
def get_recommendation(reco_id: str) -> dict:
    reco = store.RECOMMENDATIONS.get(reco_id)
    if reco is None:
        raise HTTPException(404, "Recommandation introuvable")
    return asdict(reco)


@app.post("/ai/recommendations/{reco_id}/decision")
def decide(reco_id: str, body: Decision) -> dict:
    """Décision humaine : seule voie pour appliquer une recommandation."""
    reco = store.RECOMMENDATIONS.get(reco_id)
    if reco is None:
        raise HTTPException(404, "Recommandation introuvable")
    if reco.statut != "PROPOSEE":
        raise HTTPException(409, f"Recommandation déjà traitée ou bloquée (statut {reco.statut})")
    if body.decision == "rejeter" and not body.motif:
        raise HTTPException(422, "Un motif est obligatoire pour rejeter une recommandation")
    reco.statut = "APPLIQUEE" if body.decision == "appliquer" else "REJETEE"
    if body.motif:
        reco.justification = f"{reco.justification} Motif de rejet : {body.motif}".strip()
    return asdict(reco)


@app.get("/ai/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    trace = store.TRACES.get(trace_id)
    if trace is None:
        raise HTTPException(404, "Trace introuvable")
    return trace.to_dict()


@app.get("/ai/gaps")
def list_gaps() -> list[dict]:
    return [asdict(g) for g in store.GAPS.values()]
