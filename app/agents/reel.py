"""Données réelles : séries D4D-Sénégal agrégées par le pipeline et prévisions du modèle.

Lit les fichiers de pipeline/sortie (zones, séries par zone et par heure, flux, modèles LightGBM).
Une horloge de démonstration choisit l'instant de 2013 que l'application « vit » : les agents voient
l'indice de tension de cet instant et la prévision du modèle pour les heures suivantes, jamais le futur.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Flotte de démonstration par zone : le dataset ne contient aucune donnée de bus
FLOTTE = {
    "Parcelles Assainies": (["Ligne 1", "Ligne 23"], 4), "Almadies": (["Ligne 8", "Ligne 15"], 3),
    "Grand Dakar": (["Ligne 3", "Ligne 7"], 4), "Dakar Plateau": (["Ligne 1", "Ligne 5"], 3),
    "Guediawaye": (["Ligne 11", "Ligne 20"], 3), "Pikine Dagoudane": (["Ligne 9", "Ligne 16"], 3),
    "Thiaroye": (["Ligne 12"], 2), "Niayes": (["Ligne 19"], 2), "Rufisque": (["Ligne 6"], 2),
    "Bambilor": (["Ligne 30"], 2),
}

# Journées proposées pour la démonstration (dans la période d'évaluation du modèle quand c'est possible)
JOURNEES = [
    {"t": "2013-11-12T18:00", "libelle": "Mardi ordinaire, pointe du soir"},
    {"t": "2013-11-14T12:00", "libelle": "Tamkharit (Achoura)"},
    {"t": "2013-12-22T20:00", "libelle": "Grand Magal de Touba"},
    {"t": "2013-12-31T21:00", "libelle": "Saint-Sylvestre"},
    {"t": "2013-10-15T12:00", "libelle": "Tabaski (période de réglage)"},
    {"t": "2013-08-08T12:00", "libelle": "Korité (période d'apprentissage)"},
]


@dataclass
class Reel:
    zones: list[dict]  # arr_id, zone, antennes, lon, lat
    serie: dict  # (zone, iso heure) -> ligne de la série
    voisins: dict[str, list[str]]
    seuils: dict[str, float] = field(default_factory=dict)  # seuil d'alerte du modèle par horizon
    debut: str = ""
    fin: str = ""
    resultats: dict = field(default_factory=dict)
    # Prévision à la demande : caractéristiques de toutes les heures, modèles chargés, résultats mis en cache
    caracteristiques: object = None  # DataFrame indexé par l'heure « AAAA-MM-JJTHH »
    modeles: dict = field(default_factory=dict)  # horizon (h) -> Booster LightGBM
    entrees: list = field(default_factory=list)
    _cache: dict = field(default_factory=dict)

    def noms(self) -> list[str]:
        return [z["zone"] for z in self.zones]

    def zone(self, nom: str) -> Optional[dict]:
        return next((z for z in self.zones if z["zone"] == nom), None)

    def ligne(self, nom: str, t: str) -> Optional[dict]:
        return self.serie.get((nom, t[:13]))

    def prevision(self, nom: str, t: str) -> dict[int, Optional[float]]:
        """Prévision du modèle faite à l'heure t, pour chaque horizon (calculée à la première demande de cette heure)."""
        cle = t[:13]
        if not self.modeles or self.caracteristiques is None:
            return {}
        if cle not in self._cache:
            try:
                lignes = self.caracteristiques.loc[[cle]]
            except KeyError:
                self._cache[cle] = {}
            else:
                self._cache[cle] = {
                    z: {h: round(float(v)) for h, v in zip(self.modeles, vals)}
                    for z, *vals in zip(lignes["zone_nom"],
                                        *[m.predict(lignes[self.entrees]).clip(0, 100) for m in self.modeles.values()])
                }
        return self._cache[cle].get(nom, {})


def heure(t: str) -> str:
    """Clé horaire « AAAA-MM-JJTHH »."""
    return t.replace(" ", "T")[:13]


def charger(dossier: Path) -> Optional[Reel]:
    """Charge les sorties du pipeline ; None si elles sont absentes (l'application reste en démonstration)."""
    serie_f, zones_f = dossier / "serie_zone_heure.parquet", dossier / "zones_dakar.csv"
    if not serie_f.exists() or not zones_f.exists():
        return None
    try:
        import pandas as pd
    except ModuleNotFoundError:
        log.error("pandas manquant : données réelles ignorées")
        return None

    serie = pd.read_parquet(serie_f)
    serie["t"] = pd.to_datetime(serie["t"])
    zones = pd.read_csv(zones_f, sep=";").to_dict("records")

    # Modèles de prévision : les caractéristiques sont préparées pour toute l'année (moins d'une seconde),
    # la prévision elle-même n'est calculée que pour les heures demandées (démarrage rapide)
    seuils, resultats, feats, modeles, entrees = {}, {}, None, {}, []
    modele_dir = dossier / "modele"
    if (modele_dir / "tension_1h.txt").exists():
        try:
            import lightgbm as lgb

            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))
            import modele as pipeline_modele

            feats = pipeline_modele.caracteristiques(serie)
            noms = {int(z["arr_id"]): z["zone"] for z in zones}
            feats["zone_nom"] = feats["arr_id"].map(noms)
            feats.index = feats["t"].dt.strftime("%Y-%m-%dT%H")
            modeles = {h: lgb.Booster(model_file=str(modele_dir / f"tension_{h}h.txt")) for h in pipeline_modele.HORIZONS}
            entrees = list(pipeline_modele.ENTREES)
            meta = json.loads((modele_dir / "metadonnees.json").read_text(encoding="utf-8"))
            seuils = meta.get("seuils_alerte_modele", {})
            resultats = meta.get("resultats", {})
        except Exception:
            log.exception("Modèles de prévision non chargés : l'application fonctionne sans prévision")
            feats, modeles = None, {}

    lignes = {}
    for r in serie.to_dict("records"):
        r["t"] = r["t"].strftime("%Y-%m-%dT%H:00")
        lignes[(r["zone"], r["t"][:13])] = r

    # Voisins = principales destinations depuis chaque zone (flux réels de l'année)
    voisins: dict[str, list[str]] = {}
    flux_f = dossier / "flux_zone_heure.parquet"
    if flux_f.exists():
        flux = pd.read_parquet(flux_f)
        noms = {int(z["arr_id"]): z["zone"] for z in zones}
        od = flux[(flux.origine > 0) & (flux.destination > 0)].groupby(["origine", "destination"])["deplacements"].sum()
        for (o, d), n in od.sort_values(ascending=False).items():
            if len(voisins.setdefault(noms[o], [])) < 3:
                voisins[noms[o]].append(noms[d])

    log.info("Données réelles chargées : %d zones, %d heures-zones", len(zones), len(lignes))
    return Reel(zones=zones, serie=lignes, voisins=voisins, seuils=seuils, resultats=resultats,
                debut=min(k[1] for k in lignes) + ":00", fin=max(k[1] for k in lignes) + ":00",
                caracteristiques=feats, modeles=modeles, entrees=entrees)
