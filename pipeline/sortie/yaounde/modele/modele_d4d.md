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
| **Modèle** (alerte dès 85 prévus) | **3,07** | 5,05 | 71 % | 70 % |
| Modèle, alerte dès 85 prévus | 3,07 | 5,05 | 71 % | 70 % |
| Comme maintenant | 8,83 | 11,65 | 54 % | 54 % |
| Comme la semaine dernière | 6,21 | 10,42 | 52 % | 56 % |

Le modèle réduit l'erreur de **51 %** par rapport à la meilleure référence simple (« comme la semaine dernière »). 1034 heures-zones ont réellement dépassé 85.

| Zone | Erreur moyenne | Alertes détectées | Alertes justes |
| --- | --- | --- | --- |
| Yaoundé V | 2,96 | 64 % | 61 % |
| Yaoundé III | 2,93 | 80 % | 75 % |
| Yaoundé II | 3,13 | 77 % | 79 % |
| Yaoundé I | 2,65 | 85 % | 90 % |
| Yaoundé VI | 3,11 | 57 % | 59 % |
| Yaoundé IV | 3,21 | 58 % | 56 % |
| Yaoundé VII | 3,48 | 54 % | 53 % |

Facteurs les plus utilisés : `indice_tension` (76,2 %), `heure` (15,7 %), `tension_moins_3h` (1,7 %), `tension_region` (1,6 %), `tension_moins_2h` (1,1 %), `tension_moy_3h` (0,9 %)

### Prévision à 2 h

| | Erreur moyenne (points) | RMSE | Alertes détectées | Alertes justes |
| --- | --- | --- | --- | --- |
| **Modèle** (alerte dès 84 prévus) | **4,54** | 7,06 | 74 % | 62 % |
| Modèle, alerte dès 85 prévus | 4,54 | 7,06 | 67 % | 63 % |
| Comme maintenant | 15,71 | 20,83 | 34 % | 34 % |
| Comme la semaine dernière | 6,21 | 10,42 | 52 % | 56 % |

Le modèle réduit l'erreur de **27 %** par rapport à la meilleure référence simple (« comme la semaine dernière »). 1034 heures-zones ont réellement dépassé 85.

| Zone | Erreur moyenne | Alertes détectées | Alertes justes |
| --- | --- | --- | --- |
| Yaoundé V | 4,68 | 77 % | 53 % |
| Yaoundé III | 4,51 | 85 % | 66 % |
| Yaoundé II | 4,68 | 74 % | 76 % |
| Yaoundé I | 3,56 | 77 % | 88 % |
| Yaoundé VI | 4,46 | 69 % | 49 % |
| Yaoundé IV | 4,74 | 65 % | 48 % |
| Yaoundé VII | 5,11 | 55 % | 48 % |

Facteurs les plus utilisés : `heure` (57,9 %), `indice_tension` (25,1 %), `tension_moins_3h` (4,9 %), `zone_id` (1,5 %), `tension_region` (1,5 %), `tension_moy_3h` (1,4 %)

## Lecture

- *Erreur moyenne* : écart moyen entre l'indice prévu et l'indice observé, en points (sur 100).
- *Alertes détectées* : part des vraies saturations que le modèle avait annoncées (rappel).
- *Alertes justes* : part des alertes annoncées qui se sont produites (précision).
- Limite : l'indice vient de l'activité téléphonique ; il reflète la présence et les déplacements des usagers, pas directement le trafic routier.
