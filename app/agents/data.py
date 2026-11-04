"""Accès aux données de mobilité pour les agents.

Deux sources, mêmes fonctions : les données réelles D4D-Sénégal agrégées par le pipeline (10 arrondissements
de Dakar, 2013, avec prévisions du modèle), sinon les données de démonstration ci-dessous (3 zones).
Les agents n'appellent que les fonctions de ce module.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.agents import store

REEL = None  # données réelles chargées par activer()
HORLOGE_DEFAUT = "2013-11-12T18:00"

TRAFFIC = {
    "Dakar Plateau": {"vitesse_moyenne": 12.5, "niveau_congestion": 88, "vehicules_par_heure": 4500},
    "Almadies": {"vitesse_moyenne": 35.0, "niveau_congestion": 30, "vehicules_par_heure": 1200},
    "Grand Dakar": {"vitesse_moyenne": 10.0, "niveau_congestion": 92, "vehicules_par_heure": 5100},
}

FLEET = {
    "Grand Dakar": {"lignes_actives": ["Ligne 03", "Ligne 14"], "bus_en_reserve": 4, "capacite": 60},
    "Dakar Plateau": {"lignes_actives": ["Ligne 01", "Ligne 05"], "bus_en_reserve": 2, "capacite": 60},
    "Almadies": {"lignes_actives": ["Ligne 08"], "bus_en_reserve": 5, "capacite": 60},
}

# Zones voisines : là où se reporte le trafic quand un axe ferme (utilisé par le simulateur)
NEIGHBORS = {
    "Dakar Plateau": ["Grand Dakar"],
    "Grand Dakar": ["Dakar Plateau", "Almadies"],
    "Almadies": ["Grand Dakar"],
}

# Arrêts principaux : demande (personnes qui arrivent à l'arrêt par heure) et passages de bus par heure
STOPS = [
    {"arret": "Place de l'Indépendance", "zone": "Dakar Plateau", "ligne": "Ligne 01", "demande_par_heure": 415, "bus_par_heure": 6},
    {"arret": "Gare routière Petersen", "zone": "Dakar Plateau", "ligne": "Ligne 05", "demande_par_heure": 455, "bus_par_heure": 8},
    {"arret": "Marché Sandaga", "zone": "Dakar Plateau", "ligne": "Ligne 01", "demande_par_heure": 250, "bus_par_heure": 6},
    {"arret": "Rond-point Colobane", "zone": "Grand Dakar", "ligne": "Ligne 03", "demande_par_heure": 590, "bus_par_heure": 7},
    {"arret": "Stade Iba Mar Diop", "zone": "Grand Dakar", "ligne": "Ligne 14", "demande_par_heure": 180, "bus_par_heure": 5},
    {"arret": "Liberté 6", "zone": "Grand Dakar", "ligne": "Ligne 03", "demande_par_heure": 355, "bus_par_heure": 7},
    {"arret": "Ngor Village", "zone": "Almadies", "ligne": "Ligne 08", "demande_par_heure": 95, "bus_par_heure": 4},
    {"arret": "Route des Almadies", "zone": "Almadies", "ligne": "Ligne 08", "demande_par_heure": 130, "bus_par_heure": 4},
]


def activer(dossier: Path) -> bool:
    """Charge les données réelles si le pipeline a produit ses sorties dans ce dossier."""
    from app.agents import reel

    global REEL
    REEL = reel.charger(dossier)
    return REEL is not None


def source() -> str:
    return "d4d" if REEL else "demonstration"


def horloge() -> str:
    """Instant de 2013 que « vit » l'application (données réelles seulement)."""
    return store.STATE.get("horloge", {}).get("t", HORLOGE_DEFAUT)


def regler_horloge(t: str) -> str:
    from app.agents.reel import heure

    if REEL is None:
        raise ValueError("Horloge indisponible : données de démonstration.")
    cle = heure(t)
    if not (REEL.debut[:13] <= cle <= REEL.fin[:13]):
        raise ValueError(f"Instant hors de la période des données ({REEL.debut} → {REEL.fin}).")
    if not any(REEL.ligne(z, cle) for z in REEL.noms()):
        raise ValueError("Aucune donnée à cet instant (heure manquante dans le dataset).")
    store.set_state("horloge", {"t": f"{cle}:00"})
    return f"{cle}:00"


def _propre(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def zones() -> list[str]:
    return REEL.noms() if REEL else list(TRAFFIC)


def traffic(zone: str) -> Optional[dict]:
    if REEL is None:
        return TRAFFIC.get(zone)
    if REEL.zone(zone) is None:
        return None
    # Heure absente (panne de collecte) : dernière heure connue, au plus 3 heures avant
    t = datetime.fromisoformat(horloge())
    for recul in range(4):
        ligne = REEL.ligne(zone, (t - timedelta(hours=recul)).strftime("%Y-%m-%dT%H"))
        if ligne:
            break
    else:
        return None
    prev = REEL.prevision(zone, ligne["t"])
    return {
        "niveau_congestion": int(ligne["indice_tension"]),
        "vitesse_moyenne": None,  # le dataset ne mesure pas la vitesse
        "vehicules_par_heure": int(ligne["arrivees"] + ligne["departs"]),  # déplacements de l'échantillon
        "appels": int(ligne["appels"]),
        "arrivees": int(ligne["arrivees"]),
        "departs": int(ligne["departs"]),
        "ecart_habituel": _propre(ligne.get("ecart_habituel")),
        "prevision_1h": prev.get(1),
        "prevision_2h": prev.get(2),
        "heure": ligne["t"],
        "source": "d4d",
    }


def fleet(zone: str) -> Optional[dict]:
    if REEL is None:
        return FLEET.get(zone)
    flotte = REEL.territoire.get("flotte", {}).get(zone)
    return dict(flotte) if flotte else None


def neighbors(zone: str) -> list[str]:
    return REEL.voisins.get(zone, []) if REEL else NEIGHBORS.get(zone, [])


def position(zone: str) -> Optional[dict]:
    z = REEL.zone(zone) if REEL else None
    return {"lon": z["lon"], "lat": z["lat"]} if z else None


def seuil_prevision(horizon: str = "1h") -> Optional[float]:
    """Seuil d'alerte du modèle pour cet horizon (réglé à l'entraînement), ou None sans modèle."""
    return REEL.seuils.get(horizon) if REEL else None


def historique(zone: str, heures: int = 24) -> list[dict]:
    """Observé sur les dernières heures et prévisions faites à l'heure de l'horloge."""
    if REEL is None:
        return []
    t = datetime.fromisoformat(horloge())
    out = []
    for k in range(heures, -1, -1):
        ligne = REEL.ligne(zone, (t - timedelta(hours=k)).strftime("%Y-%m-%dT%H"))
        if ligne:
            out.append({"t": ligne["t"], "observe": int(ligne["indice_tension"])})
    if REEL.ligne(zone, t.strftime("%Y-%m-%dT%H")):
        prev = REEL.prevision(zone, t.strftime("%Y-%m-%dT%H"))
        for h in (1, 2):
            p = prev.get(h)
            if p is not None:
                out.append({"t": (t + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00"), "prevu": int(p)})
    return out


def stops() -> list[dict]:
    arrets = REEL.territoire.get("arrets") if REEL else None
    return [dict(s) for s in (arrets or STOPS)]
