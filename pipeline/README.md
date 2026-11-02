# Pipeline de données D4D-Sénégal

Prépare le dataset D4D-Sénégal (Orange, 2013) pour FlowPulse : exploration, nettoyage, sélection de la région de Dakar et agrégation par arrondissement et par heure.

- Les fichiers bruts sont lus **en place, en lecture seule**, sans être décompressés ni copiés.
- Seuls des **agrégats par zone** sortent du pipeline : aucune donnée individuelle.
- Les données brutes et les sorties ne vont **jamais sur GitHub** (`pipeline/sortie/` est ignoré par git).

## Ce qu'il faut

| Élément | Détail |
| --- | --- |
| Le disque du dataset | Branché, avec le dossier `data` qui contient `SET1`, `SET2`, `SET3` et `ContextData` (par exemple `E:\data`) |
| Python 3.11 ou plus | `python --version` |
| Espace libre | Environ 1 Go sur le disque de l'ordinateur pour les sorties |

Toutes les commandes se lancent dans PowerShell, **depuis le dossier du dépôt `flowpulse-ai-service`**, là où vous l'avez cloné. Dans les exemples, `<chemin vers>` est à remplacer par l'emplacement de ce dossier sur votre machine. Sur Mac ou Linux, remplacer `.venv\Scripts\` par `.venv/bin/`.

## Étape 1 : préparer l'environnement (une seule fois)

1. Se placer dans le dossier du dépôt :

   ```powershell
   cd "<chemin vers>\flowpulse-ai-service"
   ```

2. Créer l'environnement Python, s'il n'existe pas encore (pas de dossier `.venv`) :

   ```powershell
   python -m venv .venv
   ```

3. Activer l'environnement. `(.venv)` apparaît alors au début de la ligne :

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   Si PowerShell refuse d'exécuter le script, lancer une seule fois :

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

4. Installer les dépendances du service :

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. Installer les dépendances du pipeline (DuckDB, pandas, pyarrow, LightGBM : environ 60 Mo, de 5 à 15 minutes avec une connexion lente) :

   ```powershell
   python -m pip install --default-timeout=120 --retries 10 -r pipeline\requirements.txt
   ```

## Étape 2 : vérifier le disque

1. Brancher le disque et l'ouvrir dans l'Explorateur.
2. Noter la lettre du lecteur (par exemple `E:`) et vérifier qu'il contient `data\SET1`, `data\SET2` et `data\ContextData`.

Si le disque n'apparaît pas dans l'Explorateur, ne jamais accepter « Initialiser » ou « Formater » : cela effacerait les données.

## Étape 3 : explorer les données

1. Se placer dans le dossier du dépôt (inutile si vous y êtes déjà) :

   ```powershell
   cd "<chemin vers>\flowpulse-ai-service"
   ```

2. Activer l'environnement (inutile si `(.venv)` est déjà affiché au début de la ligne) :

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

3. Régler l'encodage du terminal, pour les accents :

   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   ```

4. Lancer l'exploration, en remplaçant `E:\data` par l'emplacement du dossier `data` :

   ```powershell
   python -I pipeline\d4d.py explorer --source E:\data
   ```

- **Durée :** environ 10 minutes (lecture des 12 mois d'appels, puis de la première période de trajets).
- **Dans le terminal :** `SET1 voix (lecture des 12 mois…)`, puis `SET2 (période 1)…`, puis `Rapport : …`.
- **Ne pas fermer le terminal** pendant le traitement. Pour l'interrompre : `Ctrl + C`.

### Ce qui s'affiche

Le script annonce chaque étape et montre l'avancement au fur et à mesure :

```
[2/5] SET1 voix : lecture des 12 mois d'appels (environ 30 s par mois)
      [██████░░░░░░░░░░░░░░░░░░]  25%  3/12  SET1V_03 : 108,2 M lignes  · reste ≈ 4 min 30 s
```

### Où sont les résultats

Dans le dossier `pipeline\sortie\` du dépôt. La liste des fichiers s'affiche aussi à la fin du traitement.

| Fichier | Format | Contenu | S'ouvre avec |
| --- | --- | --- | --- |
| `exploration_d4d.md` | Markdown | Le rapport : antennes et arrondissements de Dakar, volumes par mois, heures manquantes, valeurs suspectes, rythme de l'activité, doublons des trajets, décisions de nettoyage | VS Code (clic droit → *Open Preview*), GitHub |
| `exploration_mois.csv` | CSV (`;`) | Volumes et anomalies par mois | Excel, LibreOffice |
| `exploration_dakar_par_heure.csv` | CSV (`;`) | Appels moyens à Dakar par heure de la journée | Excel, LibreOffice |
| `exploration_dakar_par_jour.csv` | CSV (`;`) | Appels moyens à Dakar par jour de la semaine | Excel, LibreOffice |
| `exploration_dakar_jours.csv` | CSV (`;`) | Appels à Dakar pour chaque jour de 2013, du plus calme au plus chargé | Excel, LibreOffice |
| `set1v_heure_antenne.parquet` | Parquet | Appels par heure et par antenne émettrice : environ 15 millions de lignes au lieu de plus d'un milliard, réutilisées par l'étape d'agrégation | Python (pandas, DuckDB), pas Excel |

**Pourquoi ces formats :**
- **Markdown** pour le rapport : lisible tel quel, affiché proprement par VS Code et GitHub, facile à reprendre dans le rapport de 5 pages.
- **CSV** pour les petits tableaux : ils s'ouvrent dans Excel pour faire des graphiques.
- **Parquet** pour les grands tableaux : 15 millions de lignes ne tiennent pas dans Excel (limite d'environ 1 million). Parquet est compressé (environ 10 fois plus petit qu'un CSV), garde les types (dates, nombres) et se relit en quelques secondes. C'est le format standard des pipelines de données.

## Étape 4 : nettoyage et agrégation

Nécessite l'étape 3 (elle réutilise `set1v_heure_antenne.parquet`).

Ce que fait l'étape :
- **Nettoyage :** suppression des doublons exacts de SET2, exclusion de la journée de panne du 29 mars 2013.
- **Sélection :** région de Dakar (10 arrondissements). Les autres antennes forment une zone « hors Dakar », utilisée seulement pour les déplacements qui entrent dans la région ou en sortent.
- **Agrégation :** pour chaque arrondissement et chaque heure de 2013, les appels (SET1), les usagers présents, les arrivées et les départs (SET2), et l'indice de tension.

1. Se placer dans le dossier du dépôt (inutile si vous y êtes déjà) :

   ```powershell
   cd "<chemin vers>\flowpulse-ai-service"
   ```

2. Activer l'environnement (inutile si `(.venv)` est déjà affiché au début de la ligne) :

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

3. Régler l'encodage du terminal :

   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   ```

4. Lancer l'agrégation, en remplaçant `E:\data` par l'emplacement du dossier `data` :

   ```powershell
   python -I pipeline\d4d.py agreger --source E:\data
   ```

- **Durée :** environ 15 à 30 minutes. La partie longue est la lecture des 25 périodes de trajets (SET2), affichée avec une barre de progression.
- **Ne pas fermer le terminal** pendant le traitement. Pour l'interrompre : `Ctrl + C`, puis relancer la même commande (l'étape repart de zéro).

### Où sont les résultats

Dans le même dossier `pipeline\sortie\` :

| Fichier | Format | Contenu | S'ouvre avec |
| --- | --- | --- | --- |
| `agregation_d4d.md` | Markdown | Le rapport : nettoyage appliqué, chiffres par zone, indice moyen par heure, principaux déplacements entre zones, définitions des colonnes | VS Code, GitHub |
| `zones_dakar.csv` | CSV (`;`) | Les 10 arrondissements : identifiant, nom, nombre d'antennes, position moyenne (longitude, latitude) | Excel |
| `serie_zone_heure.csv` | CSV (`;`) | Environ 87 000 lignes (10 zones × 8 760 heures) : `appels`, `antennes_actives`, `presents_echantillon`, `arrivees`, `departs`, `indice_tension`, `ecart_habituel` | Excel |
| `serie_zone_heure.parquet` | Parquet | La même série, pour le modèle de prévision et le service IA | Python |
| `flux_zone_heure.parquet` | Parquet | Déplacements par heure entre zones (origine → destination, zone 0 = hors Dakar) | Python |

L'**indice de tension** (0 à 100) rapporte l'activité de l'heure au haut niveau **récent** de la zone : le 99e centile de ses appels sur les **4 semaines précédentes**. Il ne regarde que le passé (rien ne fuit de l'avenir) et suit la croissance du nombre d'abonnés au fil de 2013. C'est un **indicateur de tension de mobilité** tiré de l'activité téléphonique, pas une mesure directe du trafic routier. L'**écart habituel** compare l'heure à la médiane des 8 mêmes créneaux précédents (même jour, même heure ; 1 = habituel) : il fait ressortir les événements.

Aucun de ces fichiers ne contient de donnée individuelle : uniquement des totaux par zone et par heure.

### Recalculer seulement l'indice

Si seule la définition de l'indice change (nouvelle version du script), inutile de relire le disque : l'étape `indice` repart de `serie_zone_heure.parquet` et réécrit les séries en quelques secondes.

```powershell
python -I pipeline\d4d.py indice
```

Relancer ensuite l'étape 5 (le modèle apprend sur l'indice).

## Étape 5 : entraîner le modèle de prévision

Nécessite l'étape 4. **Le disque n'est plus nécessaire** : l'entraînement part de `serie_zone_heure.parquet`. Aucune carte graphique n'est utile ; un ordinateur portable suffit (moins de 1 Go de mémoire).

Ce que fait l'étape :
- **Caractéristiques :** pour chaque zone et chaque heure, ce que l'on sait à cet instant : heure, jour, mois, jour particulier (fêtes, Magal), indice des dernières heures et de la semaine précédente, déplacements, tension moyenne de la région.
- **Apprentissage :** un modèle LightGBM par horizon (1 h et 2 h d'avance), appris de janvier à septembre 2013, réglé sur octobre.
- **Évaluation :** sur **novembre et décembre**, des semaines que le modèle n'a jamais vues, face à deux références simples : « comme maintenant » et « comme la semaine dernière à la même heure ».

1. Se placer dans le dossier du dépôt et activer l'environnement (inutile si `(.venv)` est déjà affiché) :

   ```powershell
   cd "<chemin vers>\flowpulse-ai-service"
   ```

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

2. Régler l'encodage du terminal :

   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   ```

3. Lancer l'entraînement (pas besoin de `--source`) :

   ```powershell
   python -I pipeline\d4d.py entrainer
   ```

- **Durée :** de 1 à 5 minutes.

### Où sont les résultats

Dans `pipeline\sortie\modele\` :

| Fichier | Format | Contenu | S'ouvre avec |
| --- | --- | --- | --- |
| `modele_d4d.md` | Markdown | Le rapport : erreur moyenne du modèle et des références, alertes détectées et justes, résultats par zone, facteurs les plus utilisés | VS Code, GitHub |
| `importance_caracteristiques.csv` | CSV (`;`) | Poids de chaque facteur dans les prévisions, par horizon | Excel |
| `tension_1h.txt`, `tension_2h.txt` | Texte (LightGBM) | Les modèles entraînés, rechargés par le service IA | Python (LightGBM) |
| `metadonnees.json` | JSON | Caractéristiques utilisées, périodes, jours particuliers, tous les résultats | Éditeur de texte, Python |
| `predictions_test.parquet` | Parquet | Prévisions et valeurs observées sur novembre-décembre, pour les graphiques et la démonstration | Python |

**Comment lire les résultats :**
- *Erreur moyenne* : écart moyen entre l'indice prévu et l'indice observé, en points sur 100. Plus c'est bas, mieux c'est.
- *Alertes détectées* : part des vraies saturations (indice ≥ 85) que le modèle avait annoncées.
- *Alertes justes* : part des alertes annoncées qui se sont réellement produites.
- *Seuil d'alerte du modèle* : un modèle de prévision lisse les pics (il annonce 82 quand la réalité monte à 88). Son seuil d'alerte est donc réglé sur octobre pour annoncer au moins 75 % des saturations ; le rapport montre aussi le résultat avec le seuil brut de 85.

## En cas de problème

| Message | Cause | Solution |
| --- | --- | --- |
| `No module named 'duckdb'` | Environnement non activé, ou étape 1 non faite | Vérifier que `(.venv)` est affiché, sinon refaire l'étape 1 |
| `No files found that match the pattern` | Mauvais chemin du disque | Vérifier la lettre du lecteur et le dossier `data` |
| `Out of Memory` | Mémoire de l'ordinateur insuffisante | Fermer les autres applications et relancer |
| `Résumé SET1 introuvable` | L'étape 3 n'a pas été lancée | Lancer d'abord `explorer` |
| `Séries introuvables` | L'étape 4 n'a pas été lancée | Lancer d'abord `agreger` |
| `pandas manquant` ou `lightgbm manquant` | Dépendances du pipeline non installées | Étape 1, point 5 |
| Les résultats doivent aller ailleurs | Autre dossier souhaité | Ajouter `--sortie <dossier>` à la commande |
| Caractères bizarres dans le terminal | Encodage de la console | Relancer la commande `$env:PYTHONIOENCODING = "utf-8"` |
