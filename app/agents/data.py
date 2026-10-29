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


def zones() -> list[str]:
    return list(TRAFFIC)


def traffic(zone: str) -> Optional[dict]:
    return TRAFFIC.get(zone)


def fleet(zone: str) -> Optional[dict]:
    return FLEET.get(zone)


def neighbors(zone: str) -> list[str]:
    return NEIGHBORS.get(zone, [])
