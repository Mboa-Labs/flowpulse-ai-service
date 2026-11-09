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
from typing import Literal, Optional

from app.agents import data, optimizer, policy, store, watcher
from app.langue import tr

TypeScenario = Literal["fermeture", "evenement", "renfort"]

PART_AXE = 0.35  # part de la capacité de la zone portée par l'axe fermé
REPORT = 0.6  # part du trafic de l'axe qui se reporte vers les zones voisines
PART_VOITURE = 0.35  # part des participants d'un événement qui viennent en voiture
OCCUPATION = 1.5  # personnes par voiture
# Données réelles : les déplacements observés viennent d'un échantillon d'environ 300 000 usagers (SET2) sur
# environ 9 millions d'abonnés ; on les extrapole puis on garde la part qui circule en voiture
EXTRAPOLATION = 30
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
    lieu: Optional[str] = None  # identifiant d'un lieu réel (axe, pont, stade…) ; la zone en découle

    def nom_lieu(self) -> Optional[str]:
        f = data.lieu(self.lieu) if self.lieu else None
        return f["properties"]["nom"] if f else None

    def duree_h(self) -> float:
        h1, m1 = map(int, self.debut.split(":"))
        h2, m2 = map(int, self.fin.split(":"))
        return max(0.5, ((h2 * 60 + m2) - (h1 * 60 + m1)) / 60)

    def libelle(self) -> str:
        quand = tr(f"de {self.debut} à {self.fin}", f"from {self.debut} to {self.fin}")
        nom = self.nom_lieu()
        if self.type == "fermeture":
            if nom:
                return tr(f"Fermeture temporaire : {nom} ({self.zone}) {quand}", f"Temporary closure: {nom} ({self.zone}) {quand}")
            return tr(f"Fermeture temporaire d'un axe principal à {self.zone} {quand}", f"Temporary closure of a main road in {self.zone} {quand}")
        if self.type == "evenement":
            ou = f"{nom} ({self.zone})" if nom else self.zone
            return tr(f"Événement de {self.participants:,} participants à {ou} {quand}".replace(",", " "),
                      f"Event with {self.participants:,} participants at {ou} {quand}")
        return tr(f"Renfort de {self.nb_bus} bus à {self.zone} {quand}", f"Reinforcement of {self.nb_bus} buses in {self.zone} {quand}")


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
        "vitesse_moyenne": round(vitesse_ref * tf_ref / tf, 1) if vitesse_ref else None,
        "niveau": watcher.level(round(congestion)) or "FLUIDE",
        "_tf": tf,
        "_charge": charge,
    }


def run(scenario: Scenario) -> dict:
    parts = {scenario.zone: 1.0}
    if scenario.lieu:
        f = data.lieu(scenario.lieu)
        if f is None:
            raise ValueError(f"Lieu inconnu : {scenario.lieu}.")
        scenario.zone = f["properties"]["zone"]
        # Un axe peut traverser plusieurs communes : la fermeture pèse sur chacune selon la longueur traversée
        parts = {c: p for c, p in (f["properties"].get("parts") or {scenario.zone: 1.0}).items() if data.traffic(c) is not None} or {scenario.zone: 1.0}
    if data.traffic(scenario.zone) is None:
        raise ValueError(f"Zone inconnue : {scenario.zone}. Zones disponibles : {', '.join(data.zones())}.")
    trace = store.start_trace("simulation")
    started = time.perf_counter()
    duree = scenario.duree_h()

    # Copie des données : la simulation ne touche jamais l'état réel
    base = {z: dict(t) for z in data.zones() if (t := data.traffic(z)) is not None}
    reel = any(t.get("source") == "d4d" for t in base.values())
    if reel:
        # Demande en équivalent véhicules : déplacements de l'échantillon × extrapolation × part en voiture / occupation
        for t in base.values():
            t["vehicules_par_heure"] = max(1.0, t["vehicules_par_heure"] * EXTRAPOLATION * PART_VOITURE / OCCUPATION)
    capacite = {z: t["vehicules_par_heure"] / max(t["niveau_congestion"], 1) * 100 for z, t in base.items()}
    vph = {z: float(t["vehicules_par_heure"]) for z, t in base.items()}
    cap = dict(capacite)
    z = scenario.zone

    if scenario.type == "fermeture":
        for c, part in parts.items():
            cap[c] *= 1 - PART_AXE * part
            voisins = [v for v in data.neighbors(c) if v not in parts] or [v for v in data.neighbors(c) if v != c]
            reporte = vph[c] * PART_AXE * part * REPORT if voisins else 0
            vph[c] -= reporte
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
    # (décision, type de décision) : les décisions d'un même type relèvent des mêmes textes
    a_verifier = [(scenario.libelle(), f"scenario_{scenario.type}")] if scenario.type != "renfort" else []
    for etat in apres:
        flotte = data.fleet(etat["zone"]) or {}
        if etat["niveau"] != "SATURE" or not flotte.get("bus_en_reserve"):
            continue
        nb = optimizer.buses_needed(etat["niveau_congestion"], flotte["bus_en_reserve"])
        if nb:
            a_verifier.append((tr(f"Renfort de {nb} bus de réserve sur la {flotte['lignes_actives'][0]} à {etat['zone']} "
                                  f"de {scenario.debut} à {scenario.fin}",
                                  f"Reinforcement of {nb} reserve buses on {flotte['lignes_actives'][0]} in {etat['zone']} "
                                  f"from {scenario.debut} to {scenario.fin}"), "reaffectation_bus_reserve"))
    mesures = []
    for decision, type_decision in a_verifier:
        verdict = policy.check(decision, type_decision)
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
            (tr(f"Point de départ : l'indice de tension de chaque zone à l'instant rejoué. Demande : les déplacements des "
                f"profils de mobilité, dont {round(PART_VOITURE * 100)} % en voiture. Zones voisines : principales destinations "
                f"de ces déplacements. {data.origine_donnees()}.",
                f"Starting point: each zone's tension index at the replayed time. Demand: trips from the mobility profiles, "
                f"{round(PART_VOITURE * 100)} % of them by car. Neighbouring zones: main destinations of these trips. "
                f"Mobility profiles from Dakar (D4D-Senegal, 2013) transposed onto the 7 communes of Yaoundé.")
             if reel else data.origine_donnees()),
            tr("Temps de parcours : fonction BPR (1 + 0,15 × charge⁴), standard en ingénierie du trafic.",
               "Travel time: BPR function (1 + 0.15 × load⁴), a standard in traffic engineering."),
            tr(f"Fermeture : l'axe porte {round(PART_AXE * 100)} % de la capacité de la zone ; {round(REPORT * 100)} % de son trafic se reporte sur les zones voisines.",
               f"Closure: the road carries {round(PART_AXE * 100)} % of the zone's capacity; {round(REPORT * 100)} % of its traffic shifts to neighbouring zones.")
            + (tr(f" L'axe traverse {', '.join(f'{c} ({round(p * 100)} %)' for c, p in parts.items())} : l'effet est réparti selon la longueur traversée.",
                  f" The road crosses {', '.join(f'{c} ({round(p * 100)} %)' for c, p in parts.items())}: the effect is shared by the length crossed.")
               if scenario.type == "fermeture" and len(parts) > 1 else ""),
            *([tr(f"Lieu : {scenario.nom_lieu()}, tracé OpenStreetMap (© contributeurs OSM, ODbL). Le calcul reste fait à l'échelle des communes.",
                  f"Place: {scenario.nom_lieu()}, OpenStreetMap trace (© OSM contributors, ODbL). The computation stays at commune level.")]
              if scenario.lieu else []),
            tr(f"Événement : {round(PART_VOITURE * 100)} % des participants viennent en voiture ({OCCUPATION} personnes par véhicule), arrivées réparties sur la durée.",
               f"Event: {round(PART_VOITURE * 100)} % of participants come by car ({OCCUPATION} people per vehicle), arrivals spread over the duration."),
            tr(f"Renfort : chaque bus transporte {PASSAGERS_BUS_HEURE} passagers par heure, dont {round(REPORT_MODAL * 100)} % auraient pris leur voiture.",
               f"Reinforcement: each bus carries {PASSAGERS_BUS_HEURE} passengers per hour, {round(REPORT_MODAL * 100)} % of whom would otherwise drive."),
        ],
        "trace_id": trace.id,
        "date": time.time(),
    }
    store.put_simulation(simulation)
    return simulation
