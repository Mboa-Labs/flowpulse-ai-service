# Sorties du pipeline D4D-Sénégal

Fichiers produits par `pipeline/d4d.py` (étapes `explorer`, `agreger`, `indice`, `entrainer`) à partir du dataset D4D-Sénégal (Orange / Sonatel, 2013). Le service IA les charge au démarrage ; sans eux, il fonctionne sur des données de démonstration.

| Fichier | Contenu |
| --- | --- |
| `zones_dakar.csv` | Les 10 arrondissements de la région de Dakar, nombre d'antennes, position moyenne |
| `serie_zone_heure.parquet` | Par arrondissement et par heure de 2013 : appels, présents (échantillon), arrivées, départs, indice de tension |
| `flux_zone_heure.parquet` | Déplacements par heure entre arrondissements (échantillon SET2) |
| `modele/` | Modèles LightGBM de prévision à 1 h et 2 h, métadonnées, rapport d'évaluation, prévisions de la période de test |
| `exploration_d4d.md`, `agregation_d4d.md`, `exploration_*.csv` | Rapports et tableaux de l'exploration et de l'agrégation |

**Aucune donnée individuelle** : uniquement des totaux par arrondissement et par heure, et des modèles entraînés sur ces totaux. Les données brutes du D4D ne sont pas dans ce dépôt et ne doivent pas y être ajoutées. Le résumé par antenne (`set1v_heure_antenne.parquet`) et la copie CSV des séries restent locaux.

Source : Y.-A. de Montjoye et al., *D4D-Senegal: The Second Mobile Phone Data for Development Challenge*, 2014. Utilisation soumise aux conditions du programme D4D.
