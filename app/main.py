"""Service IA FlowPulse : pipeline de données, modèles, agents et base de connaissances.

Routes : santé, recherche dans la base de connaissances, superviseur (Orchestrator),
surveillance (Watcher + Optimizer + Policy), simulation What-If, recommandations, traces et manques réglementaires.
"""

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import kb, persistence
from app.agents import data, orchestrator, simulator, store, watcher
from app.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    persistence.init(persistence.connect(settings.database_url))
    data.activer(settings.dossier_donnees())
    yield
    persistence.flush()


app = FastAPI(title="FlowPulse AI service", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def save_changes(request: Request, call_next):
    """Après chaque requête, enregistre ce que les agents ont créé ou modifié."""
    response = await call_next(request)
    await run_in_threadpool(persistence.flush)
    return response


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


HEURE = r"^([01]\d|2[0-3]):[0-5]\d$"


class ScenarioIn(BaseModel):
    type: Literal["fermeture", "evenement", "renfort"]
    zone: str
    debut: str = Field("08:00", pattern=HEURE)
    fin: str = Field("12:00", pattern=HEURE)
    participants: int = Field(0, ge=0, le=200_000)
    nb_bus: int = Field(0, ge=0, le=50)
    lieu: Optional[str] = Field(None, max_length=80, pattern=r"^[a-z0-9-]+$")


class AlertAction(BaseModel):
    action: Literal["acquitter", "transmettre"]
    par: str = Field(..., min_length=1, max_length=120)
    destinataire: Optional[str] = Field(None, max_length=120)
    note: Optional[str] = Field(None, max_length=500)


class Decision(BaseModel):
    decision: Literal["appliquer", "rejeter"]
    motif: Optional[str] = None


class HorlogeIn(BaseModel):
    t: str = Field(..., pattern=r"^2013-\d{2}-\d{2}[T ]\d{2}(:\d{2})?$")


@app.get("/ai/zones")
def zones() -> list[dict]:
    """Vue d'ensemble par zone à l'heure de l'horloge : tension, prévision, flotte, position et niveau d'alerte."""
    out = []
    for z in data.zones():
        t, f = data.traffic(z), data.fleet(z)
        if t is None:
            continue
        out.append({"zone": z, **t, **(f or {}), **(data.position(z) or {}),
                    "niveau": watcher.level(t["niveau_congestion"]) or "FLUIDE"})
    return out


@app.get("/ai/zones/serie")
def zone_serie(zone: str, heures: int = Query(24, ge=1, le=168)) -> list[dict]:
    """Indice observé sur les dernières heures et prévisions du modèle à 1 h et 2 h, pour une zone."""
    if zone not in data.zones():
        raise HTTPException(404, "Zone inconnue")
    return data.historique(zone, heures)


@app.get("/ai/horloge")
def get_horloge() -> dict:
    """Source des données et, pour les données réelles, l'instant de 2013 rejoué et les journées proposées."""
    if data.REEL is None:
        return {"source": data.source(), "t": None, "journees": []}
    t = data.REEL.territoire
    return {"source": data.source(), "t": data.horloge(), "debut": data.REEL.debut, "fin": data.REEL.fin,
            "journees": t.get("journees", []), "modele": bool(data.REEL.seuils), "seuils_alerte": data.REEL.seuils,
            "territoire": t.get("nom"), "pays": t.get("pays"), "mention": t.get("mention"),
            "correspondance": t.get("correspondance")}


@app.get("/ai/territoire/carte")
def carte() -> dict:
    """Contours des zones (GeoJSON) pour la carte ; vide si le territoire n'en fournit pas (repères ponctuels)."""
    if data.REEL is None or not data.REEL.territoire.get("contours"):
        return {"type": "FeatureCollection", "features": []}
    return data.REEL.territoire["contours"]


@app.get("/ai/lieux")
def lieux() -> dict:
    """Lieux réels proposés pour les simulations (OpenStreetMap) : axes, ponts, carrefours, stades, marchés."""
    return {"type": "FeatureCollection", "features": data.lieux()}


@app.post("/ai/horloge")
def set_horloge(body: HorlogeIn) -> dict:
    """Change l'instant rejoué ; les écrans et les agents travaillent alors sur ce moment de 2013."""
    try:
        data.regler_horloge(body.t)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return get_horloge()


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
    return watcher.last_run()


@app.post("/ai/simulations")
def simulate(body: ScenarioIn) -> dict:
    """Simulation What-If : effet d'un scénario sur le trafic et mesures vérifiées, sans rien appliquer."""
    try:
        return simulator.run(simulator.Scenario(**body.model_dump()))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/ai/simulations")
def list_simulations() -> list[dict]:
    return sorted((s for s in store.SIMULATIONS.values() if data.zone_connue(s["scenario"]["zone"])),
                  key=lambda s: s["date"], reverse=True)


@app.get("/ai/simulations/{sim_id}")
def get_simulation(sim_id: str) -> dict:
    sim = store.SIMULATIONS.get(sim_id)
    if sim is None:
        raise HTTPException(404, "Simulation introuvable")
    return sim


@app.post("/ai/alerts/{alert_id}/action")
def alert_action(alert_id: str, body: AlertAction) -> dict:
    """Acquittement ou transmission d'une alerte (le backend fournit l'auteur et journalise)."""
    if body.action == "transmettre" and not body.destinataire:
        raise HTTPException(422, "Indiquez à qui transmettre l'alerte")
    try:
        return watcher.update_alert(alert_id, body.action, body.par, body.destinataire, body.note)
    except KeyError:
        raise HTTPException(404, "Alerte introuvable dans la dernière surveillance")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/ai/stops")
def stops() -> list[dict]:
    """Offre et demande par arrêt : tension = demande / capacité offerte (F2.1)."""
    out = []
    for s in data.stops():
        capacite = (data.fleet(s["zone"]) or {}).get("capacite", 60)
        offre = s["bus_par_heure"] * capacite
        tension = round(s["demande_par_heure"] / offre * 100)
        attente = round(60 / s["bus_par_heure"] / 2 * max(1, tension / 100), 1)
        out.append({**s, "offre_par_heure": offre, "tension": tension, "attente_min": attente,
                    "niveau": "SATURE" if tension >= 100 else "DENSE" if tension >= 80 else "FLUIDE"})
    return sorted(out, key=lambda s: s["tension"], reverse=True)


@app.get("/ai/kb/documents")
def kb_documents() -> dict:
    """Inventaire de la base de connaissances et état de la dernière indexation."""
    try:
        collections = kb.stats()
    except Exception:
        collections = {c: 0 for c in kb.COLLECTIONS}
    return {"documents": kb.documents(), "collections": collections, "indexation": kb.INDEXATION}


@app.post("/ai/kb/reindex")
def kb_reindex() -> dict:
    """Relance l'indexation des textes (quelques minutes, nécessite Ollama et nomic-embed-text)."""
    try:
        return kb.reindex()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))


@app.get("/ai/recommendations")
def list_recommendations() -> list[dict]:
    """Recommandations du territoire affiché (celles d'un autre territoire restent dans le journal)."""
    return [asdict(r) for r in store.RECOMMENDATIONS.values() if data.zone_connue(r.zone)]


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
    store.mark("recommandation", reco.id)
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
