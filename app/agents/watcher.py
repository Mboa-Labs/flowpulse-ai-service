"""Agent de surveillance (Watcher).

Règles déterministes, sans modèle de langage : il tourne toutes les X minutes, doit être rapide
et ses décisions doivent être explicables. Il lève une alerte au-dessus du seuil et demande
une recommandation à l'Optimizer.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
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
        alerts.append(Alert(zone, niveau, t["niveau_congestion"], t["vitesse_moyenne"], reco.id if reco else None))
    store.set_state("derniere_surveillance", {"trace_id": trace.id, "alertes": [asdict(a) for a in alerts]})
    return trace.id, alerts


def last_run() -> dict:
    """Résultat du dernier passage de surveillance (conservé au redémarrage)."""
    return store.STATE.get("derniere_surveillance", {"trace_id": None, "alertes": []})
