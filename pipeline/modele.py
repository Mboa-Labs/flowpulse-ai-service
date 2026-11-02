"""Modèle de prévision de l'indice de tension par zone (étape « entrainer » de pipeline/d4d.py).

Entrée : les séries agrégées par l'étape « agreger » (pipeline/sortie/serie_zone_heure.parquet).
Le disque du dataset n'est plus nécessaire.

Le modèle (LightGBM, gradient boosting) prévoit l'indice de tension de chaque zone 1 heure et
2 heures à l'avance. Il est comparé à deux références simples ; on ne retient le modèle que s'il
fait mieux qu'elles sur des semaines qu'il n'a jamais vues.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError:
    raise SystemExit("pandas manquant : installer les dépendances du pipeline (README, étape 1, point 5).")

HORIZONS = (1, 2)  # heures d'avance
SEUIL_ALERTE = 85  # indice à partir duquel FlowPulse lève une alerte « saturé »

# Découpage dans le temps : on apprend sur le passé, on règle sur octobre, on juge sur novembre-décembre
FIN_APPRENTISSAGE = "2013-10-01"
FIN_VALIDATION = "2013-11-01"

# Jours particuliers au Sénégal en 2013 (fériés et grands événements religieux)
JOURS_PARTICULIERS = {
    "2013-01-01": "Jour de l'an", "2013-01-24": "Maouloud", "2013-04-01": "Lundi de Pâques",
    "2013-04-04": "Fête de l'indépendance", "2013-05-01": "Fête du travail", "2013-05-09": "Ascension",
    "2013-05-20": "Lundi de Pentecôte", "2013-08-08": "Korité", "2013-08-15": "Assomption",
    "2013-10-15": "Tabaski", "2013-11-01": "Toussaint", "2013-11-14": "Tamkharit",
    "2013-12-22": "Grand Magal de Touba", "2013-12-25": "Noël", "2013-12-31": "Saint-Sylvestre",
}


def caracteristiques(serie: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par zone et par heure, avec ce que le modèle sait à cet instant (jamais le futur)."""
    df = serie.copy()
    df["t"] = pd.to_datetime(df["t"])
    # Grille horaire complète par zone : les heures absentes deviennent des valeurs manquantes, jamais inventées
    grille = pd.MultiIndex.from_product(
        [sorted(df["arr_id"].unique()), pd.date_range(df["t"].min(), df["t"].max(), freq="h")], names=["arr_id", "t"])
    df = df.set_index(["arr_id", "t"]).reindex(grille).reset_index()
    df["mouvements"] = df["arrivees"] + df["departs"]
    # Correction partielle du biais des données d'appels : déplacements rapportés aux usagers vus
    df["mouvements_par_present"] = df["mouvements"] / df["presents_echantillon"].replace(0, np.nan)

    g = df.groupby("arr_id", group_keys=False)
    for k in (1, 2, 3, 24, 168):
        df[f"tension_moins_{k}h"] = g["indice_tension"].shift(k)
    df["tension_moy_3h"] = g["indice_tension"].transform(lambda s: s.rolling(3, min_periods=2).mean())
    df["arrivees_moins_1h"] = g["arrivees"].shift(1)
    df["mouvements_moins_1h"] = g["mouvements"].shift(1)

    # Pression régionale : tension moyenne de toutes les zones à la même heure
    df["tension_region"] = df.groupby("t")["indice_tension"].transform("mean")

    df["heure"] = df["t"].dt.hour
    df["jour_semaine"] = df["t"].dt.dayofweek  # 0 = lundi
    df["week_end"] = (df["jour_semaine"] >= 5).astype(int)
    df["mois"] = df["t"].dt.month
    df["jour_particulier"] = df["t"].dt.strftime("%Y-%m-%d").isin(JOURS_PARTICULIERS).astype(int)
    df["zone_id"] = df["arr_id"].astype("category")
    return df


ENTREES = [
    "zone_id", "heure", "jour_semaine", "week_end", "mois", "jour_particulier",
    "indice_tension", "tension_moins_1h", "tension_moins_2h", "tension_moins_3h", "tension_moins_24h",
    "tension_moins_168h", "tension_moy_3h", "ecart_habituel", "tension_region",
    "arrivees", "departs", "mouvements_moins_1h", "arrivees_moins_1h", "mouvements_par_present", "antennes_actives",
]


def mesures(vrai: np.ndarray, prevu: np.ndarray) -> dict:
    ok = ~np.isnan(vrai) & ~np.isnan(prevu)
    v, p = vrai[ok], prevu[ok]
    alerte_v, alerte_p = v >= SEUIL_ALERTE, p >= SEUIL_ALERTE
    vrais_positifs = int((alerte_v & alerte_p).sum())
    return {
        "erreur_moyenne": round(float(np.abs(v - p).mean()), 2),  # en points d'indice
        "rmse": round(float(np.sqrt(((v - p) ** 2).mean())), 2),
        "alertes_reelles": int(alerte_v.sum()),
        "alertes_detectees": round(vrais_positifs / max(1, int(alerte_v.sum())), 3),  # rappel
        "alertes_justes": round(vrais_positifs / max(1, int(alerte_p.sum())), 3),  # précision
        "points": int(ok.sum()),
    }


def entrainer(sortie: Path, av) -> Path:
    try:
        import lightgbm as lgb
    except ModuleNotFoundError:
        raise SystemExit("lightgbm manquant : installer les dépendances du pipeline (README, étape 1, point 5).")

    fichier = sortie / "serie_zone_heure.parquet"
    if not fichier.exists():
        raise SystemExit("Séries introuvables : lancer d'abord l'étape « agreger ».")
    dossier = sortie / "modele"
    dossier.mkdir(exist_ok=True)

    av.etape("Préparation des caractéristiques (heure, jour, valeurs récentes, flux, jours particuliers)")
    serie = pd.read_parquet(fichier)
    zones = serie.drop_duplicates("arr_id").set_index("arr_id")["zone"].to_dict()
    df = caracteristiques(serie)
    av.fin(f"{len(df):,} lignes, {len(ENTREES)} caractéristiques".replace(",", " "))

    resultats, importances, predictions = {}, [], []
    av.etape(f"Apprentissage : {len(HORIZONS)} modèles (prévision à {', '.join(f'{h} h' for h in HORIZONS)})")
    for i, h in enumerate(HORIZONS, 1):
        g = df.groupby("arr_id", group_keys=False)
        df["cible"] = g["indice_tension"].shift(-h)
        # Références simples : « comme maintenant » et « comme la semaine dernière à la même heure »
        df["ref_persistance"] = df["indice_tension"]
        df["ref_semaine"] = g["indice_tension"].shift(168 - h)

        connu = df.dropna(subset=["cible", "indice_tension"])
        app = connu[connu["t"] < FIN_APPRENTISSAGE]
        val = connu[(connu["t"] >= FIN_APPRENTISSAGE) & (connu["t"] < FIN_VALIDATION)]
        test = connu[connu["t"] >= FIN_VALIDATION]

        modele = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.03, num_leaves=63, min_child_samples=40,
                                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
        modele.fit(app[ENTREES], app["cible"], eval_set=[(val[ENTREES], val["cible"])], eval_metric="l1",
                   callbacks=[lgb.early_stopping(100, verbose=False)])
        prevu = np.clip(modele.predict(test[ENTREES], num_iteration=modele.best_iteration_), 0, 100)

        resultats[f"{h}h"] = {
            "modele": mesures(test["cible"].to_numpy(), prevu),
            "reference_persistance": mesures(test["cible"].to_numpy(), test["ref_persistance"].to_numpy(dtype=float)),
            "reference_semaine": mesures(test["cible"].to_numpy(), test["ref_semaine"].to_numpy(dtype=float)),
            "par_zone": {zones[z]: mesures(t["cible"].to_numpy(), prevu[(test["arr_id"] == z).to_numpy()])
                         for z, t in test.groupby("arr_id")},
            "arbres": int(modele.best_iteration_),
        }
        modele.booster_.save_model(str(dossier / f"tension_{h}h.txt"), num_iteration=modele.best_iteration_)
        importances.append(pd.DataFrame({"horizon": f"{h}h", "caracteristique": ENTREES,
                                         "importance": modele.booster_.feature_importance("gain")}))
        predictions.append(pd.DataFrame({"t": test["t"], "arr_id": test["arr_id"], "horizon_h": h,
                                         "observe": test["cible"], "prevu": prevu.round(1)}))
        r = resultats[f"{h}h"]
        av.barre(i, len(HORIZONS), f"à {h} h : erreur moyenne {r['modele']['erreur_moyenne']} points "
                                   f"(référence {r['reference_persistance']['erreur_moyenne']})")
    av.fin()

    av.etape("Fichiers et rapport")
    imp = pd.concat(importances)
    imp["importance"] = (imp["importance"] / imp.groupby("horizon")["importance"].transform("sum") * 100).round(1)
    imp.sort_values(["horizon", "importance"], ascending=[True, False]).to_csv(
        dossier / "importance_caracteristiques.csv", sep=";", index=False, encoding="utf-8-sig")
    preds = pd.concat(predictions)
    # Instant de la prévision = instant observé moins l'horizon
    preds["t"] = preds["t"] + pd.to_timedelta(preds["horizon_h"], unit="h")
    preds.to_parquet(dossier / "predictions_test.parquet", index=False)
    meta = {
        "cible": "indice_tension (0 à 100) de chaque arrondissement de Dakar",
        "horizons_h": list(HORIZONS), "entrees": ENTREES, "seuil_alerte": SEUIL_ALERTE,
        "apprentissage": f"2013-01-01 → {FIN_APPRENTISSAGE}", "validation": f"{FIN_APPRENTISSAGE} → {FIN_VALIDATION}",
        "test": f"{FIN_VALIDATION} → 2013-12-31", "zones": {int(k): v for k, v in zones.items()},
        "jours_particuliers": JOURS_PARTICULIERS, "resultats": resultats,
    }
    (dossier / "metadonnees.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (dossier / "modele_d4d.md").write_text(rapport(meta, imp), encoding="utf-8")
    av.fin()
    return dossier


def rapport(meta: dict, imp: pd.DataFrame) -> str:
    lignes = ["# Modèle de prévision de la tension par zone", "",
              "Généré par `pipeline/d4d.py entrainer` à partir de `serie_zone_heure.parquet`.", "",
              "## Ce que fait le modèle", "",
              "Il prévoit l'**indice de tension** (0 à 100) de chacun des 10 arrondissements de Dakar, "
              f"**{' et '.join(f'{h} heure' + ('s' if h > 1 else '') for h in meta['horizons_h'])} à l'avance**, "
              "à partir de l'heure, du jour, des valeurs des dernières heures et de la semaine précédente, "
              "des déplacements entre zones et des jours particuliers (fêtes, Magal).", "",
              f"- Apprentissage : {meta['apprentissage']} ; réglage : {meta['validation']} ; "
              f"**évaluation sur des semaines jamais vues** : {meta['test']}.",
              "- Références : « comme maintenant » (persistance) et « comme la semaine dernière à la même heure ».",
              f"- Alerte : indice prévu ≥ {meta['seuil_alerte']}.", "",
              "## Résultats sur la période de test", ""]
    for h, r in meta["resultats"].items():
        m, p, s = r["modele"], r["reference_persistance"], r["reference_semaine"]
        gain = 1 - m["erreur_moyenne"] / p["erreur_moyenne"] if p["erreur_moyenne"] else 0
        lignes += [f"### Prévision à {h.replace('h', ' h')}", "",
                   "| | Erreur moyenne (points) | RMSE | Alertes détectées | Alertes justes |",
                   "| --- | --- | --- | --- | --- |",
                   f"| **Modèle** | **{m['erreur_moyenne']}** | {m['rmse']} | {m['alertes_detectees']:.0%} | {m['alertes_justes']:.0%} |",
                   f"| Comme maintenant | {p['erreur_moyenne']} | {p['rmse']} | {p['alertes_detectees']:.0%} | {p['alertes_justes']:.0%} |",
                   f"| Comme la semaine dernière | {s['erreur_moyenne']} | {s['rmse']} | {s['alertes_detectees']:.0%} | {s['alertes_justes']:.0%} |",
                   "", f"Le modèle réduit l'erreur de **{gain:.0%}** par rapport à la meilleure intuition simple "
                   f"(« comme maintenant »). {m['alertes_reelles']} heures-zones ont réellement dépassé {meta['seuil_alerte']}.", "",
                   "| Zone | Erreur moyenne | Alertes détectées | Alertes justes |", "| --- | --- | --- | --- |"]
        lignes += [f"| {z} | {v['erreur_moyenne']} | {v['alertes_detectees']:.0%} | {v['alertes_justes']:.0%} |"
                   for z, v in r["par_zone"].items()]
        top = imp[imp["horizon"] == h].sort_values("importance", ascending=False).head(6)
        lignes += ["", "Facteurs les plus utilisés : " + ", ".join(f"`{c}` ({v} %)" for c, v in
                                                                 zip(top["caracteristique"], top["importance"])), ""]
    lignes += ["## Lecture", "",
               "- *Erreur moyenne* : écart moyen entre l'indice prévu et l'indice observé, en points (sur 100).",
               "- *Alertes détectées* : part des vraies saturations que le modèle avait annoncées (rappel).",
               "- *Alertes justes* : part des alertes annoncées qui se sont produites (précision).",
               "- Limite : l'indice vient de l'activité téléphonique ; il reflète la présence et les déplacements "
               "des usagers, pas directement le trafic routier.", ""]
    return "\n".join(lignes)
