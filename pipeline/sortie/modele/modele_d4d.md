# Modèle de prévision de la tension par zone

Généré par `pipeline/d4d.py entrainer` à partir de `serie_zone_heure.parquet`.

## Ce que fait le modèle

Il prévoit l'**indice de tension** (0 à 100) de chacun des 10 arrondissements de Dakar, **1 heure et 2 heures à l'avance**, à partir de l'heure, du jour, des valeurs des dernières heures et de la semaine précédente, des déplacements entre zones et des jours particuliers (fêtes, Magal).

- Apprentissage : 2013-01-01 → 2013-10-01 ; réglage : 2013-10-01 → 2013-11-01 ; **évaluation sur des semaines jamais vues** : 2013-11-01 → 2013-12-31.
- Références : « comme maintenant » (persistance) et « comme la semaine dernière à la même heure ».
- Saturation : indice observé ≥ 85. Le modèle lissant les pics, son seuil d'alerte est réglé sur octobre pour annoncer au moins 75 % des saturations.
- Les repères de l'indice (niveau haut et niveau habituel de chaque zone) sont calculés sur la période d'apprentissage seulement : rien ne fuit des mois d'évaluation.

## Résultats sur la période de test

### Prévision à 1 h

| | Erreur moyenne (points) | RMSE | Alertes détectées | Alertes justes |
| --- | --- | --- | --- | --- |
| **Modèle** (alerte dès 85 prévus) | **3,11** | 5,19 | 69 % | 66 % |
| Modèle, alerte dès 85 prévus | 3,11 | 5,19 | 69 % | 66 % |
| Comme maintenant | 8,97 | 11,89 | 50 % | 50 % |
| Comme la semaine dernière | 6,11 | 10,14 | 52 % | 56 % |

Le modèle réduit l'erreur de **49 %** par rapport à la meilleure référence simple (« comme la semaine dernière »). 1315 heures-zones ont réellement dépassé 85.

| Zone | Erreur moyenne | Alertes détectées | Alertes justes |
| --- | --- | --- | --- |
| Parcelles Assainies | 2,97 | 76 % | 64 % |
| Almadies | 2,82 | 80 % | 77 % |
| Grand Dakar | 3 | 78 % | 81 % |
| Dakar Plateau | 2,56 | 86 % | 89 % |
| Guediawaye | 3,09 | 60 % | 60 % |
| Pikine Dagoudane | 3,16 | 60 % | 56 % |
| Thiaroye | 3,25 | 59 % | 54 % |
| Niayes | 3,21 | 51 % | 46 % |
| Rufisque | 3,44 | 57 % | 52 % |
| Bambilor | 3,59 | 48 % | 45 % |

Facteurs les plus utilisés : `indice_tension` (68,8 %), `heure` (22,5 %), `tension_region` (1,9 %), `tension_moins_3h` (1,7 %), `tension_moins_2h` (1,2 %), `tension_moy_3h` (0,8 %)

### Prévision à 2 h

| | Erreur moyenne (points) | RMSE | Alertes détectées | Alertes justes |
| --- | --- | --- | --- | --- |
| **Modèle** (alerte dès 84 prévus) | **4,58** | 7,18 | 72 % | 58 % |
| Modèle, alerte dès 85 prévus | 4,58 | 7,18 | 66 % | 60 % |
| Comme maintenant | 15,92 | 21,12 | 29 % | 29 % |
| Comme la semaine dernière | 6,11 | 10,14 | 52 % | 56 % |

Le modèle réduit l'erreur de **25 %** par rapport à la meilleure référence simple (« comme la semaine dernière »). 1315 heures-zones ont réellement dépassé 85.

| Zone | Erreur moyenne | Alertes détectées | Alertes justes |
| --- | --- | --- | --- |
| Parcelles Assainies | 4,56 | 82 % | 54 % |
| Almadies | 4,44 | 80 % | 68 % |
| Grand Dakar | 4,49 | 75 % | 73 % |
| Dakar Plateau | 3,34 | 74 % | 90 % |
| Guediawaye | 4,48 | 74 % | 53 % |
| Pikine Dagoudane | 4,72 | 70 % | 51 % |
| Thiaroye | 4,83 | 77 % | 48 % |
| Niayes | 4,7 | 52 % | 41 % |
| Rufisque | 5 | 62 % | 51 % |
| Bambilor | 5,25 | 59 % | 41 % |

Facteurs les plus utilisés : `heure` (58,6 %), `indice_tension` (16,7 %), `tension_region` (9,1 %), `tension_moins_3h` (4,6 %), `zone_id` (2 %), `tension_moins_2h` (1,5 %)

## Lecture

- *Erreur moyenne* : écart moyen entre l'indice prévu et l'indice observé, en points (sur 100).
- *Alertes détectées* : part des vraies saturations que le modèle avait annoncées (rappel).
- *Alertes justes* : part des alertes annoncées qui se sont produites (précision).
- Limite : l'indice vient de l'activité téléphonique ; il reflète la présence et les déplacements des usagers, pas directement le trafic routier.
