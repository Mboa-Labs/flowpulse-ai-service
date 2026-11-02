"""Données de démonstration (zones de Dakar), en attendant le pipeline alimenté par le dataset.

Le pipeline remplacera ces dictionnaires par des lectures en base ; les agents ne dépendent
que des deux fonctions ci-dessous.
"""

from __future__ import annotations

from typing import Optional

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


def zones() -> list[str]:
    return list(TRAFFIC)


def traffic(zone: str) -> Optional[dict]:
    return TRAFFIC.get(zone)


def fleet(zone: str) -> Optional[dict]:
    return FLEET.get(zone)


def neighbors(zone: str) -> list[str]:
    return NEIGHBORS.get(zone, [])


def stops() -> list[dict]:
    return [dict(s) for s in STOPS]
