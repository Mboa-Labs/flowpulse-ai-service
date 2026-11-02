# Agrégation du dataset D4D-Sénégal : région de Dakar

Source : `E:\data` (lecture seule). Généré par `pipeline/d4d.py agreger`.

## Nettoyage et sélection appliqués

- Région de Dakar seulement : 10 arrondissements ; les autres antennes forment une zone « hors Dakar » utilisée uniquement pour les déplacements qui entrent dans la région ou en sortent.
- Journées exclues (panne de collecte) : 2013-03-29.
- SET2, période 1 : 14 489 136 doublons supprimés sur 44 403 074 positions (32,6 %) ; même règle sur les 25 périodes.
- Déplacement : deux positions successives du même usager, dans deux zones différentes, à moins de 2 heures.
- Aucune donnée individuelle dans les fichiers produits : uniquement des totaux par zone et par heure.

## Séries produites

- 87 305 lignes (zone × heure), 8 731 heures, du 2013-01-01 00:00:00 au 2013-12-31 23:00:00.
- Heures-zones en tension forte (indice ≥ 85) : 9 351 ; en tension (≥ 75) : 18 135.

| Zone | Appels moyens par heure | Présents moyens (échantillon) | Arrivées (année) | Départs (année) | Indice moyen | Heures ≥ 85 |
| --- | --- | --- | --- | --- | --- | --- |
| Parcelles Assainies | 39 156 | 5 076 | 7 190 448 | 6 967 460 | 44 | 847 |
| Almadies | 28 636 | 3 629 | 5 817 404 | 5 784 493 | 49 | 1 410 |
| Grand Dakar | 38 531 | 4 892 | 8 658 299 | 8 768 259 | 48 | 1 503 |
| Dakar Plateau | 42 776 | 5 169 | 5 421 331 | 5 901 687 | 38 | 718 |
| Guediawaye | 19 769 | 2 787 | 4 242 816 | 4 150 731 | 42 | 777 |
| Pikine Dagoudane | 19 160 | 2 576 | 4 428 385 | 4 420 289 | 46 | 910 |
| Thiaroye | 18 791 | 2 550 | 3 624 743 | 3 584 603 | 44 | 818 |
| Niayes | 15 309 | 2 263 | 2 510 172 | 2 396 228 | 40 | 695 |
| Rufisque | 11 184 | 1 468 | 1 169 466 | 1 162 188 | 44 | 753 |
| Bambilor | 8 826 | 1 282 | 1 681 081 | 1 650 410 | 45 | 920 |

### Indice de tension moyen par heure (jours ouvrés)

| Heure | Indice moyen |
| --- | --- |
| 0 | 18 |
| 1 | 6 |
| 2 | 3 |
| 3 | 1 |
| 4 | 1 |
| 5 | 2 |
| 6 | 3 |
| 7 | 11 |
| 8 | 24 |
| 9 | 44 |
| 10 | 62 |
| 11 | 72 |
| 12 | 76 |
| 13 | 69 |
| 14 | 60 |
| 15 | 67 |
| 16 | 64 |
| 17 | 66 |
| 18 | 70 |
| 19 | 73 |
| 20 | 83 |
| 21 | 80 |
| 22 | 67 |
| 23 | 42 |

### Principaux déplacements entre zones (échantillon SET2, toute l'année)

| Origine | Destination | Déplacements |
| --- | --- | --- |
| Dakar Plateau | Grand Dakar | 2 900 927 |
| Grand Dakar | Dakar Plateau | 2 727 207 |
| Grand Dakar | Parcelles Assainies | 2 490 708 |
| Parcelles Assainies | Grand Dakar | 2 311 022 |
| Almadies | Grand Dakar | 2 026 707 |
| Grand Dakar | Almadies | 2 023 554 |
| Almadies | Parcelles Assainies | 1 917 671 |
| Parcelles Assainies | Almadies | 1 878 839 |
| Parcelles Assainies | Guediawaye | 1 635 747 |
| Guediawaye | Parcelles Assainies | 1 605 571 |

## Définitions

- `appels` : appels émis depuis les antennes de la zone pendant l'heure (tous les abonnés Orange, SET1).
- `presents_echantillon` : usagers de l'échantillon SET2 vus dans la zone pendant l'heure.
- `arrivees`, `departs` : déplacements de l'échantillon SET2 qui entrent dans la zone ou en sortent pendant l'heure.
- `indice_tension` (0 à 100) : activité de l'heure rapportée au haut niveau habituel de la zone (99e centile de janvier au 2013-10-01, période d'apprentissage du modèle). C'est un indicateur de tension de mobilité, pas une mesure du trafic routier.
- `ecart_habituel` : activité rapportée à la médiane de la zone pour le même jour de la semaine et la même heure (1 = habituel, 1,5 = 50 % au-dessus), calculée sur la même période ; sert à repérer les événements.

_Durée de l'agrégation : 12 min 48 s._
