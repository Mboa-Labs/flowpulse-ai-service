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
    besoin = buses_needed(trafic["niveau_congestion"], flotte["bus_en_reserve"])
    nb = besoin if nb_bus is None else max(0, min(int(nb_bus), flotte["bus_en_reserve"]))
    description = (
        f"Déplacer {nb} bus de la réserve vers la {ligne} à {zone} "
        f"(congestion {trafic['niveau_congestion']} %, {flotte['bus_en_reserve']} bus en réserve)."
    )
    store.record("optimizer", "calcul_plan", {"zone": zone, "ligne": ligne, "demande": nb_bus}, description, started)

    verdict = policy.check(f"Réaffectation de bus de réserve sur une ligne urbaine : {description}")
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
    store.put_recommendation(reco)
    return reco
