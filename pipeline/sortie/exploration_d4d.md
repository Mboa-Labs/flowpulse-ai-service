# Exploration du dataset D4D-Sénégal

Source : `E:\data` (lecture seule). Généré par `pipeline/d4d.py explorer`.

## Contexte

- 1666 antennes (sites), 123 arrondissements.
- Région de Dakar : 10 arrondissements, 489 antennes.

| ARR_ID | Arrondissement | Antennes |
| --- | --- | --- |
| 1 | PARCELLES ASSAINIES | 68 |
| 2 | ALMADIES | 74 |
| 3 | GRAND DAKAR | 73 |
| 4 | DAKAR PLATEAU | 74 |
| 5 | GUEDIAWAYE | 44 |
| 6 | PIKINE DAGOUDANE | 30 |
| 7 | THIAROYE | 39 |
| 8 | NIAYES | 32 |
| 9 | RUFISQUE | 27 |
| 10 | BAMBILOR | 28 |

## SET1 voix : appels entre antennes, par heure

| Mois | Lignes | Heures présentes | Heures attendues | Appels | Durée ≥ 3600 s | Durée nulle | Appels sur la même antenne |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2013-01 | 105 818 106 | 744 | 744 | 297 964 952 | 278 380 | 0 | 50 041 723 |
| 2013-02 | 97 158 954 | 672 | 672 | 270 780 776 | 298 129 | 0 | 45 944 700 |
| 2013-03 | 107 214 266 | 722 | 744 | 303 578 065 | 471 381 | 0 | 51 990 250 |
| 2013-04 | 110 163 760 | 720 | 720 | 309 202 586 | 543 814 | 0 | 51 554 034 |
| 2013-05 | 117 244 592 | 741 | 744 | 330 844 491 | 608 239 | 0 | 55 079 960 |
| 2013-06 | 117 023 583 | 720 | 720 | 330 455 854 | 514 170 | 0 | 54 313 461 |
| 2013-07 | 117 670 426 | 742 | 744 | 313 719 224 | 604 797 | 0 | 48 938 357 |
| 2013-08 | 122 405 545 | 744 | 744 | 335 868 443 | 645 421 | 0 | 53 859 505 |
| 2013-09 | 117 489 962 | 720 | 720 | 321 378 942 | 435 595 | 0 | 50 426 258 |
| 2013-10 | 134 269 891 | 744 | 744 | 383 127 197 | 576 792 | 0 | 62 209 429 |
| 2013-11 | 122 784 281 | 720 | 720 | 344 991 182 | 511 595 | 0 | 56 410 398 |
| 2013-12 | 136 269 408 | 744 | 744 | 389 542 290 | 517 960 | 0 | 62 140 902 |

- Lignes dont une antenne est absente de la table des sites : 0
- Part des appels émis depuis la région de Dakar : 53.8%
- Heures totalement absentes de l'année : 27 (exemples : 2013-03-29 02, 2013-03-29 03, 2013-03-29 04, 2013-03-29 05, 2013-03-29 06, 2013-03-29 07, 2013-03-29 08, 2013-03-29 09, 2013-03-29 10, 2013-03-29 11)

### Rythme de l'activité à Dakar

| Heure | Appels moyens émis depuis Dakar |
| --- | --- |
| 0 | 111 040 |
| 1 | 45 273 |
| 2 | 18 995 |
| 3 | 9 386 |
| 4 | 7 760 |
| 5 | 9 484 |
| 6 | 16 673 |
| 7 | 50 874 |
| 8 | 118 373 |
| 9 | 221 638 |
| 10 | 325 458 |
| 11 | 391 920 |
| 12 | 424 855 |
| 13 | 389 580 |
| 14 | 339 614 |
| 15 | 372 000 |
| 16 | 354 135 |
| 17 | 366 317 |
| 18 | 381 284 |
| 19 | 401 348 |
| 20 | 440 916 |
| 21 | 422 012 |
| 22 | 357 174 |
| 23 | 232 465 |

| Jour | Appels moyens par jour |
| --- | --- |
| dimanche | 4 980 478 |
| lundi | 5 833 132 |
| mardi | 5 987 288 |
| mercredi | 6 011 610 |
| jeudi | 5 954 094 |
| vendredi | 5 893 138 |
| samedi | 5 880 498 |

Jours les plus calmes : 2013-03-29 (Fri) (89 991), 2013-12-22 (Sun) (3 122 089), 2013-01-24 (Thu) (3 316 880), 2013-01-27 (Sun) (3 854 627), 2013-07-20 (Sat) (3 875 670)

Jours les plus chargés : 2013-08-07 (Wed) (7 716 427), 2013-08-09 (Fri) (7 802 606), 2013-10-15 (Tue) (7 923 063), 2013-10-14 (Mon) (8 047 445), 2013-12-31 (Tue) (8 163 274)

- Antennes de Dakar actives moins de 300 jours sur 365 : 30

## SET2 : positions des usagers échantillonnés (période 1)

- 44 403 074 positions  319 508 usagers  du 2013-01-07 00:00:00 au 2013-01-20 23:50:00.
- Doublons exacts (même usager  même minute  même antenne) : 12 454 474 (28.0%).
- Positions sur une antenne inconnue : 0.
- Usagers vus au moins une fois dans la région de Dakar : 173 398 (54%)  25 677 017 positions.

## Décisions de nettoyage et de sélection

- Garder la région de Dakar (arrondissements 1 à 10), qui correspond aux zones de FlowPulse.
- SET1 : activité par antenne émettrice ; écarter les lignes dont l'antenne est inconnue ; les durées plafonnées ne servent pas (on compte des appels, pas des minutes).
- SET2 : supprimer les doublons exacts ; un déplacement = deux positions successives du même usager dans deux arrondissements différents, à moins de 2 heures d'écart.
- Heures manquantes : laissées absentes et signalées, jamais inventées.

_Durée de l'exploration : 9 min 29 s._
