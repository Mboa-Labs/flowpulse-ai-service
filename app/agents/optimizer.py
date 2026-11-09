"""Agent d'optimisation de la flotte.

Calcule une réaffectation de bus de réserve vers une ligne en tension, la fait vérifier par
l'agent Politique, puis l'enregistre comme PROPOSITION. Il n'applique jamais rien lui-même :
c'est l'opérateur qui valide dans l'interface.
"""

from __future__ import annotations

import math
import time
from typing import Optional

from app.agents import data, policy, store

SEUIL_CIBLE = 70  # niveau de congestion visé après renfort (%)


def buses_needed(congestion: int, reserve: int) -> int:
    """Un bus de renfort par tranche de 10 points au-dessus du seuil cible, dans la limite de la réserve."""
    return max(0, min(reserve, math.ceil((congestion - SEUIL_CIBLE) / 10)))


def propose(zone: str, ligne: Optional[str] = None, nb_bus: Optional[int] = None) -> store.Recommendation:
    started = time.perf_counter()
    flotte = data.fleet(zone)
    trafic = data.traffic(zone)
    if flotte is None or trafic is None:
        raise ValueError(f"Zone inconnue : {zone}. Zones disponibles : {', '.join(data.zones())}.")

    ligne = ligne if ligne in flotte["lignes_actives"] else flotte["lignes_actives"][0]
    # Le besoin se calcule sur la tension attendue : la plus forte entre maintenant et la prévision à 1 h
    tension = max(trafic["niveau_congestion"], trafic.get("prevision_1h") or 0)
    besoin = buses_needed(tension, flotte["bus_en_reserve"])
    # Un nombre absent ou nul (fréquent quand le modèle de langage remplit l'outil) vaut « le besoin calculé »
    nb = besoin if not nb_bus or int(nb_bus) <= 0 else min(int(nb_bus), flotte["bus_en_reserve"])
    if nb == 0:
        raison = ("aucun bus en réserve" if not flotte["bus_en_reserve"]
                  else f"tension attendue {tension:.0f}/100, sous le seuil de renfort ({SEUIL_CIBLE})")
        raise ValueError(f"Aucune réaffectation proposée à {zone} : {raison}.")
    description = (
        f"Déplacer {nb} bus de la réserve vers la {ligne} à {zone} "
        f"(congestion {trafic['niveau_congestion']} %, {flotte['bus_en_reserve']} bus en réserve)."
    )
    store.record("optimizer", "calcul_plan", {"zone": zone, "ligne": ligne, "demande": nb_bus}, description, started)

    verdict = policy.check(f"Réaffectation de bus de réserve sur une ligne urbaine : {description}",
                           type_decision="reaffectation_bus_reserve")
    trace = store.current_trace()
    reco = store.Recommendation(
        id=store.new_id("R"),
        zone=zone,
        ligne=ligne,
        nb_bus=nb,
        description=description,
        statut="BLOQUEE" if verdict.verdict == "NON_CONFORME" else "PROPOSEE",
        conformite=verdict.verdict,
        justification=verdict.justification,
        citations=verdict.citations,
        trace_id=trace.id if trace else None,
    )
    # Une seule proposition en attente par zone : la précédente est remplacée, pas supprimée (traçabilité)
    for old in store.RECOMMENDATIONS.values():
        if old.zone == zone and old.statut == "PROPOSEE":
            old.statut = "REMPLACEE"
            old.justification = f"{old.justification} Remplacée par {reco.id}.".strip()
            store.mark("recommandation", old.id)
    store.put_recommendation(reco)
    return reco
