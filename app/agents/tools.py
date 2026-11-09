"""Outils mis à disposition de l'Orchestrator (repris des agents écrits par Martin).

Changement clé : la réaffectation n'est plus exécutée par l'agent. L'outil crée une
recommandation PROPOSÉE, vérifiée par l'agent Politique, que l'opérateur valide ou rejette.
"""

from __future__ import annotations

import time

from langchain_core.tools import tool

from app import kb
from app.agents import data, optimizer, store
from app.langue import tr


@tool
def get_traffic_data(zone_name: str) -> str:
    """Récupère l'état de mobilité d'une zone : indice de tension, prévision à 1 h et 2 h, activité et déplacements."""
    started = time.perf_counter()
    t = data.traffic(zone_name)
    if t is None:
        out = tr(f"Aucune donnée pour la zone {zone_name}. Zones disponibles : {', '.join(data.zones())}.",
                 f"No data for zone {zone_name}. Available zones: {', '.join(data.zones())}.")
    elif t.get("source") == "d4d":
        prev = (tr(f" | Prévu dans 1 h: {t['prevision_1h']:.0f}/100, dans 2 h: {t['prevision_2h']:.0f}/100",
                   f" | Forecast in 1 h: {t['prevision_1h']:.0f}/100, in 2 h: {t['prevision_2h']:.0f}/100")
                if t.get("prevision_1h") is not None and t.get("prevision_2h") is not None else "")
        out = tr(f"Zone: {zone_name} | Heure: {t['heure']} | Congestion: {t['niveau_congestion']}% (indice de tension)"
                 f"{prev} | Appels: {t['appels']}/h | Déplacements (échantillon): {t['arrivees']} arrivées, {t['departs']} départs",
                 f"Zone: {zone_name} | Time: {t['heure']} | Congestion: {t['niveau_congestion']}% (tension index)"
                 f"{prev} | Calls: {t['appels']}/h | Trips (sample): {t['arrivees']} arrivals, {t['departs']} departures")
    else:
        out = tr(f"Zone: {zone_name} | Vitesse: {t['vitesse_moyenne']} km/h | Congestion: {t['niveau_congestion']}% | Flux: {t['vehicules_par_heure']} véh/h",
                 f"Zone: {zone_name} | Speed: {t['vitesse_moyenne']} km/h | Congestion: {t['niveau_congestion']}% | Flow: {t['vehicules_par_heure']} veh/h")
    store.record("outil", "get_traffic_data", zone_name, out, started)
    return out


@tool
def get_city_overview() -> str:
    """Vue d'ensemble de la ville : toutes les zones classées de la plus tendue à la plus calme, avec leur prévision à 1 h.
    À utiliser pour « quelle zone est la plus saturée », « où faut-il renforcer » ou toute question sur plusieurs zones."""
    started = time.perf_counter()
    lignes = []
    for z in data.zones():
        t = data.traffic(z)
        if t is None:
            continue
        prev = t.get("prevision_1h")
        lignes.append((t["niveau_congestion"], f"{z} : {t['niveau_congestion']}/100"
                       + (tr(f", prévu {prev:.0f}/100 dans 1 h", f", forecast {prev:.0f}/100 in 1 h") if prev is not None else "")))
    lignes.sort(key=lambda x: -x[0])
    out = (tr("Zones de la plus tendue à la plus calme (dense dès 75, saturé dès 85) :\n",
              "Zones from most to least under pressure (dense from 75, saturated from 85):\n") + "\n".join(f"- {l}" for _, l in lignes)
           if lignes else tr("Aucune donnée de zone disponible.", "No zone data available."))
    store.record("outil", "get_city_overview", "toutes les zones", out, started)
    return out


@tool
def get_bus_fleet_status(zone_name: str) -> str:
    """Récupère l'état des bus disponibles en réserve et les lignes actives pour une zone."""
    started = time.perf_counter()
    f = data.fleet(zone_name)
    out = (
        tr(f"Aucune information de flotte pour la zone {zone_name}.", f"No fleet information for zone {zone_name}.")
        if f is None
        else tr(f"Zone: {zone_name} | Lignes: {', '.join(f['lignes_actives'])} | Bus en réserve: {f['bus_en_reserve']} | Capacité: {f['capacite']} places",
                f"Zone: {zone_name} | Lines: {', '.join(f['lignes_actives'])} | Reserve buses: {f['bus_en_reserve']} | Capacity: {f['capacite']} seats")
    )
    store.record("outil", "get_bus_fleet_status", zone_name, out, started)
    return out


@tool
def propose_fleet_reallocation(zone_name: str, target_line: str, num_bus_to_add: int) -> str:
    """Propose de déplacer des bus de la réserve vers une ligne en tension. La proposition est
    vérifiée réglementairement puis soumise à l'opérateur ; elle n'est jamais appliquée automatiquement."""
    try:
        reco = optimizer.propose(zone_name, target_line, num_bus_to_add)
    except ValueError as e:
        return str(e)
    sources = "; ".join(f"{c['reference'] or c['titre']} {c['article']}".strip() for c in reco.citations) or tr("aucun texte applicable", "no applicable text")
    return (
        tr(f"Recommandation {reco.id} créée (statut {reco.statut}, en attente de validation par l'opérateur) : "
           f"{reco.description} Conformité : {reco.conformite}. {reco.justification} Sources : {sources}.",
           f"Recommendation {reco.id} created (status {reco.statut}, awaiting the operator's approval): "
           f"{reco.description} Compliance: {reco.conformite}. {reco.justification} Sources: {sources}.")
    )


@tool
def search_regulations(question: str) -> str:
    """Cherche dans les textes réglementaires (lois, décrets, stratégies) les passages pertinents pour une question."""
    started = time.perf_counter()
    try:
        passages = kb.search(question, n=4)
    except Exception as e:
        passages = []
        store.record("outil", "search_regulations", question, f"indisponible : {e}", started)
    if not passages:
        return tr("Aucun texte trouvé dans la base de connaissances.", "No text found in the knowledge base.")
    sources = [{"doc_id": p.doc_id, "titre": p.titre, "reference": p.reference, "article": p.article, "score": p.score} for p in passages]
    store.record("outil", "search_regulations", question, f"{len(passages)} passages", started, sources)
    return "\n".join(f"- {p.titre} ({p.reference}) {p.article} : {p.texte[:400]}" for p in passages)


TOOLS = [get_city_overview, get_traffic_data, get_bus_fleet_status, propose_fleet_reallocation, search_regulations]
TOOL_MAP = {t.name: t for t in TOOLS}
