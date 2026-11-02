"""Agent de surveillance (Watcher).

Règles déterministes, sans modèle de langage : il tourne toutes les X minutes, doit être rapide
et ses décisions doivent être explicables. Il lève une alerte au-dessus du seuil et demande
une recommandation à l'Optimizer.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.agents import data, optimizer, store

SEUIL_DENSE = 75
SEUIL_SATURE = 85


@dataclass
class Alert:
    zone: str
    niveau: str  # DENSE ou SATURE
    congestion: int
    vitesse_moyenne: float
    recommendation_id: Optional[str]
    id: str = ""
    statut: str = "NOUVELLE"  # NOUVELLE, ACQUITTEE, TRANSMISE
    plan_contingence: list[str] = field(default_factory=list)
    historique: list[dict] = field(default_factory=list)


def contingence(zone: str, niveau: str, nb_bus: int) -> list[str]:
    """Plan de contingence type : actions déterministes, à adapter par le gestionnaire."""
    flotte = data.fleet(zone) or {}
    lignes = ", ".join(flotte.get("lignes_actives", [])) or "les lignes de la zone"
    plan = [f"Prévenir l'exploitant des lignes {lignes} et la régulation de la circulation."]
    if nb_bus:
        plan.append(f"Engager {nb_bus} bus de réserve (recommandation à valider dans Flotte).")
    if niveau == "SATURE":
        plan.append("Informer les usagers aux arrêts de la zone : attente prolongée, itinéraires de délestage.")
        plan.append("Demander un agent de régulation aux carrefours principaux pendant le pic.")
    else:
        plan.append("Surveiller l'évolution : nouvelle analyse dans 15 minutes.")
    return plan


def level(congestion: int) -> Optional[str]:
    if congestion >= SEUIL_SATURE:
        return "SATURE"
    if congestion >= SEUIL_DENSE:
        return "DENSE"
    return None



def run() -> tuple[str, list[Alert]]:
    trace = store.start_trace("surveillance")
    alerts: list[Alert] = []
    for zone in data.zones():
        started = time.perf_counter()
        t = data.traffic(zone)
        niveau = level(t["niveau_congestion"])
        store.record("watcher", "analyse_zone", zone, niveau or "normal", started)
        if niveau is None:
            continue
        reco = optimizer.propose(zone) if niveau == "SATURE" else None
        alerts.append(Alert(
            zone, niveau, t["niveau_congestion"], t["vitesse_moyenne"], reco.id if reco else None,
            id=store.new_id("A"), plan_contingence=contingence(zone, niveau, reco.nb_bus if reco else 0),
        ))
    store.set_state("derniere_surveillance", {"trace_id": trace.id, "alertes": [asdict(a) for a in alerts]})
    return trace.id, alerts


def last_run() -> dict:
    """Résultat du dernier passage de surveillance (conservé au redémarrage)."""
    return store.STATE.get("derniere_surveillance", {"trace_id": None, "alertes": []})


def update_alert(alert_id: str, action: str, par: str, destinataire: Optional[str] = None, note: Optional[str] = None) -> dict:
    """Acquitte ou transmet une alerte de la dernière surveillance ; chaque geste est historisé."""
    run_ = last_run()
    alerte = next((a for a in run_["alertes"] if a.get("id") == alert_id), None)
    if alerte is None:
        raise KeyError(alert_id)
    if action == "acquitter":
        if alerte["statut"] != "NOUVELLE":
            raise ValueError(f"Alerte déjà {alerte['statut'].lower()}")
        alerte["statut"] = "ACQUITTEE"
    else:
        alerte["statut"] = "TRANSMISE"
    alerte["historique"].append({"action": action, "par": par, "destinataire": destinataire, "note": note, "date": time.time()})
    store.set_state("derniere_surveillance", run_)
    return alerte
