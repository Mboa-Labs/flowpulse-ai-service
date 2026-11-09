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
from app.langue import tr

SEUIL_DENSE = 75
SEUIL_SATURE = 85


@dataclass
class Alert:
    zone: str
    niveau: str  # DENSE ou SATURE
    congestion: int
    vitesse_moyenne: Optional[float]
    recommendation_id: Optional[str]
    id: str = ""
    prevision_1h: Optional[float] = None
    prevision_2h: Optional[float] = None
    prevue: bool = False  # vraie si l'alerte vient de la prévision du modèle et non de l'état actuel
    heure: Optional[str] = None  # instant de la donnée (horloge de démonstration)
    statut: str = "NOUVELLE"  # NOUVELLE, ACQUITTEE, TRANSMISE
    plan_contingence: list[str] = field(default_factory=list)
    historique: list[dict] = field(default_factory=list)


def contingence(zone: str, niveau: str, nb_bus: int, prevue: bool = False) -> list[str]:
    """Plan de contingence type : actions déterministes, à adapter par le gestionnaire."""
    flotte = data.fleet(zone) or {}
    lignes = ", ".join(flotte.get("lignes_actives", [])) or tr("les lignes de la zone", "the zone's lines")
    plan = [tr(f"Prévenir l'exploitant des lignes {lignes} et la régulation de la circulation.",
               f"Notify the operator of {lignes} and traffic control.")]
    if prevue:
        plan.insert(0, tr("Saturation prévue dans l'heure par le modèle : agir avant le pic.",
                          "Saturation expected within the hour by the model: act before the peak."))
    if nb_bus:
        plan.append(tr(f"Engager {nb_bus} bus de réserve (recommandation à valider dans Flotte).",
                       f"Deploy {nb_bus} reserve buses (recommendation to approve in Fleet)."))
    if niveau == "SATURE":
        plan.append(tr("Informer les usagers aux arrêts de la zone : attente prolongée, itinéraires de délestage.",
                       "Inform passengers at the zone's stops: longer waits, alternative routes."))
        plan.append(tr("Demander un agent de régulation aux carrefours principaux pendant le pic.",
                       "Request a traffic officer at the main junctions during the peak."))
    else:
        plan.append(tr("Surveiller l'évolution : nouvelle analyse dans 15 minutes.",
                       "Monitor the trend: new analysis in 15 minutes."))
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
    seuil = data.seuil_prevision("1h")
    for zone in data.zones():
        started = time.perf_counter()
        t = data.traffic(zone)
        if t is None:
            store.record("watcher", "analyse_zone", zone, "aucune donnée à cet instant", started)
            continue
        niveau = level(t["niveau_congestion"])
        # Anticipation : le modèle prévoit une saturation dans l'heure alors que la zone n'est pas encore saturée
        p1 = t.get("prevision_1h")
        prevue = seuil is not None and p1 is not None and p1 >= seuil and niveau != "SATURE"
        if prevue:
            niveau = "SATURE"
        detail = niveau or "normal"
        if p1 is not None:
            detail += (f" (indice {t['niveau_congestion']}, prévu {p1:.0f} dans 1 h, seuil d'alerte {seuil:.0f})"
                       if seuil is not None else f" (prévu {p1:.0f} dans 1 h)")
        store.record("watcher", "analyse_zone", zone, detail, started)
        if niveau is None:
            continue
        reco = optimizer.propose(zone) if niveau == "SATURE" else None
        alerts.append(Alert(
            zone, niveau, t["niveau_congestion"], t["vitesse_moyenne"], reco.id if reco else None,
            id=store.new_id("A"), plan_contingence=contingence(zone, niveau, reco.nb_bus if reco else 0, prevue),
            prevision_1h=p1, prevision_2h=t.get("prevision_2h"), prevue=prevue, heure=t.get("heure"),
        ))
    store.set_state("derniere_surveillance", {"trace_id": trace.id, "alertes": [asdict(a) for a in alerts]})
    return trace.id, alerts


def last_run() -> dict:
    """Résultat du dernier passage de surveillance (conservé au redémarrage)."""
    run_ = store.STATE.get("derniere_surveillance", {"trace_id": None, "alertes": []})
    # Une surveillance faite sur un autre territoire (par exemple avant le passage à Yaoundé) n'est pas affichée
    alertes = [a for a in run_["alertes"] if data.zone_connue(a["zone"])]
    return {**run_, "alertes": alertes} if len(alertes) == len(run_["alertes"]) else {"trace_id": None, "alertes": alertes}


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
