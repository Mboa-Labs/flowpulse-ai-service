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

5. Installer la dépendance du pipeline (DuckDB, environ 20 Mo) :

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

À venir : `pipeline\d4d.py agreger`, qui produira les séries par arrondissement de Dakar et par heure (activité, arrivées, départs, flux entre zones) utilisées par le modèle de prévision.

## En cas de problème

| Message | Cause | Solution |
| --- | --- | --- |
| `No module named 'duckdb'` | Environnement non activé, ou étape 1 non faite | Vérifier que `(.venv)` est affiché, sinon refaire l'étape 1 |
| `No files found that match the pattern` | Mauvais chemin du disque | Vérifier la lettre du lecteur et le dossier `data` |
| `Out of Memory` | Mémoire de l'ordinateur insuffisante | Fermer les autres applications et relancer |
| Caractères bizarres dans le terminal | Encodage de la console | Relancer la commande `$env:PYTHONIOENCODING = "utf-8"` |
