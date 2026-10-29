"""Agent Simulateur What-If (bac à sable du nœud Sandbox de Y.3172).

Teste un scénario (fermeture d'axe, événement, renfort de bus) sur une copie des données,
sans rien modifier ni proposer à l'opérateur. Le modèle de trafic est volontairement simple
et explicable : capacité par zone, report du trafic vers les zones voisines et temps de
parcours selon la fonction BPR (Bureau of Public Roads). Les mesures d'accompagnement sont
vérifiées par l'agent Politique, comme toute décision.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Literal

from app.agents import data, optimizer, policy, store, watcher

TypeScenario = Literal["fermeture", "evenement", "renfort"]

PART_AXE = 0.35  # part de la capacité de la zone portée par l'axe fermé
REPORT = 0.6  # part du trafic de l'axe qui se reporte vers les zones voisines
PART_VOITURE = 0.35  # part des participants d'un événement qui viennent en voiture
OCCUPATION = 1.5  # personnes par voiture
PASSAGERS_BUS_HEURE = 120  # 60 places, 2 rotations par heure
REPORT_MODAL = 0.25  # part des passagers d'un bus de renfort qui auraient pris leur voiture


@dataclass
class Scenario:
    type: TypeScenario
    zone: str
    debut: str = "08:00"
    fin: str = "12:00"
    participants: int = 0
    nb_bus: int = 0

    def duree_h(self) -> float:
        h1, m1 = map(int, self.debut.split(":"))
        h2, m2 = map(int, self.fin.split(":"))
        return max(0.5, ((h2 * 60 + m2) - (h1 * 60 + m1)) / 60)

    def libelle(self) -> str:
        quand = f"de {self.debut} à {self.fin}"
        if self.type == "fermeture":
            return f"Fermeture temporaire d'un axe principal à {self.zone} {quand}"
        if self.type == "evenement":
            return f"Événement de {self.participants:,} participants à {self.zone} {quand}".replace(",", " ")
        return f"Renfort de {self.nb_bus} bus à {self.zone} {quand}"


def temps_parcours(congestion: float) -> float:
    """Facteur de temps de parcours (BPR) : 1 à vide, croissance rapide près de la saturation."""
    return 1 + 0.15 * (congestion / 100) ** 4


def _etat(zone: str, vph: float, capacite: float, vitesse_ref: float, tf_ref: float) -> dict:
    charge = vph / capacite * 100  # peut dépasser 100 % : la demande excède la capacité
    tf = temps_parcours(charge)
    congestion = min(100.0, charge)
    return {
        "zone": zone,
        "niveau_congestion": round(congestion),
        "charge": round(charge),
        "surcharge": charge > 100,
        "vehicules_par_heure": round(vph),
        "vitesse_moyenne": round(vitesse_ref * tf_ref / tf, 1),
        "niveau": watcher.level(round(congestion)) or "FLUIDE",
        "_tf": tf,
        "_charge": charge,
    }


def run(scenario: Scenario) -> dict:
    if data.traffic(scenario.zone) is None:
        raise ValueError(f"Zone inconnue : {scenario.zone}. Zones disponibles : {', '.join(data.zones())}.")
    trace = store.start_trace("simulation")
    started = time.perf_counter()
    duree = scenario.duree_h()

    # Copie des données : la simulation ne touche jamais l'état réel
    base = {z: dict(data.traffic(z)) for z in data.zones()}
    capacite = {z: t["vehicules_par_heure"] / max(t["niveau_congestion"], 1) * 100 for z, t in base.items()}
    vph = {z: float(t["vehicules_par_heure"]) for z, t in base.items()}
    cap = dict(capacite)
    z = scenario.zone

    if scenario.type == "fermeture":
        cap[z] *= 1 - PART_AXE
        voisins = data.neighbors(z)
        reporte = vph[z] * PART_AXE * REPORT if voisins else 0
        vph[z] -= reporte
        for v in voisins:
            vph[v] += reporte / len(voisins)
    elif scenario.type == "evenement":
        vph[z] += scenario.participants * PART_VOITURE / OCCUPATION / duree
    else:
        vph[z] = max(0.0, vph[z] - scenario.nb_bus * PASSAGERS_BUS_HEURE * REPORT_MODAL / OCCUPATION)
    store.record("simulator", "modele_trafic", asdict(scenario), {k: round(v) for k, v in vph.items()}, started)

    avant, apres = [], []
    for zone, t in base.items():
        tf_ref = temps_parcours(t["niveau_congestion"])
        avant.append(_etat(zone, t["vehicules_par_heure"], capacite[zone], t["vitesse_moyenne"], tf_ref))
        apres.append(_etat(zone, vph[zone], cap[zone], t["vitesse_moyenne"], tf_ref))

    total = sum(vph.values())
    temps = sum(a["_tf"] / b["_tf"] * vph[a["zone"]] for a, b in zip(apres, avant)) / total - 1
    touchees = [a for a, b in zip(apres, avant) if abs(a["_charge"] - b["_charge"]) >= 2]
    personnes = sum(a["vehicules_par_heure"] for a in touchees) * OCCUPATION * duree + scenario.participants
    if scenario.type == "renfort":
        personnes += scenario.nb_bus * PASSAGERS_BUS_HEURE * duree  # passagers transportés par le renfort
    pire_apres, pire_avant = max(zip(apres, avant), key=lambda p: abs(p[0]["_charge"] - p[1]["_charge"]))
    lignes = (data.fleet(pire_apres["zone"]) or {}).get("lignes_actives", [])
    indicateurs = {
        "temps_parcours_pct": round(temps * 100),
        "zones_saturees_avant": sum(1 for a in avant if a["niveau"] == "SATURE"),
        "zones_saturees_apres": sum(1 for a in apres if a["niveau"] == "SATURE"),
        "zone_la_plus_touchee": pire_apres["zone"],
        "variation_max_points": round(pire_apres["_charge"] - pire_avant["_charge"]),
        "ligne_la_plus_touchee": lignes[0] if lignes else None,
        "personnes_concernees": int(round(personnes, -2)),
    }
    store.record("simulator", "indicateurs", scenario.libelle(), indicateurs, started)

    # Mesures d'accompagnement : renfort là où une zone sature, puis vérification réglementaire
    a_verifier = [scenario.libelle()] if scenario.type != "renfort" else []
    for etat in apres:
        flotte = data.fleet(etat["zone"]) or {}
        if etat["niveau"] != "SATURE" or not flotte.get("bus_en_reserve"):
            continue
        nb = optimizer.buses_needed(etat["niveau_congestion"], flotte["bus_en_reserve"])
        if nb:
            a_verifier.append(f"Renfort de {nb} bus de réserve sur la {flotte['lignes_actives'][0]} à {etat['zone']} de {scenario.debut} à {scenario.fin}")
    mesures = []
    for decision in a_verifier:
        verdict = policy.check(decision)
        mesures.append({"description": decision, "verdict": verdict.verdict, "justification": verdict.justification, "citations": verdict.citations})

    for e in avant + apres:
        e.pop("_tf")
        e.pop("_charge")
    simulation = {
        "id": store.new_id("S"),
        "scenario": asdict(scenario),
        "libelle": scenario.libelle(),
        "avant": avant,
        "apres": apres,
        "indicateurs": indicateurs,
        "mesures": mesures,
        "hypotheses": [
            "Modèle de démonstration : capacité par zone et temps de parcours BPR (1 + 0,15 × charge⁴), en attendant le dataset.",
            f"Fermeture : l'axe porte {round(PART_AXE * 100)} % de la capacité de la zone ; {round(REPORT * 100)} % de son trafic se reporte sur les zones voisines.",
            f"Événement : {round(PART_VOITURE * 100)} % des participants viennent en voiture ({OCCUPATION} personnes par véhicule), arrivées réparties sur la durée.",
            f"Renfort : chaque bus transporte {PASSAGERS_BUS_HEURE} passagers par heure, dont {round(REPORT_MODAL * 100)} % auraient pris leur voiture.",
        ],
        "trace_id": trace.id,
        "date": time.time(),
    }
    store.SIMULATIONS[simulation["id"]] = simulation
    return simulation
