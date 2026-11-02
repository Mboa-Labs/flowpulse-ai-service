"""Découpage dans le temps, partagé par l'agrégation et l'entraînement.

Les repères de l'indice de tension (niveau haut, niveau habituel) sont calculés sur la période
d'apprentissage seulement : le modèle ne doit rien savoir des mois sur lesquels il est jugé.
"""

FIN_APPRENTISSAGE = "2013-10-01"  # janvier → septembre : apprentissage
FIN_VALIDATION = "2013-11-01"  # octobre : réglage ; novembre → décembre : évaluation
